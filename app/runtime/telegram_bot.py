import asyncio
import httpx
from app.config import settings
from app.database import SessionLocal, LogModel, MessageModel
from app.runtime.workflow import WorkflowRunner, broadcast_ws

class TelegramBotWorker:
    def __init__(self):
        self.token = settings.TELEGRAM_BOT_TOKEN
        self.api_url = f"https://api.telegram.org/bot{self.token}" if self.token else None
        self.offset = 0
        self.running = False
        self.task = None

    def log(self, level: str, message: str):
        db = SessionLocal()
        try:
            log_entry = LogModel(
                level=level,
                message=f"[Telegram Bot] {message}",
                component="telegram"
            )
            db.add(log_entry)
            db.commit()
            print(f"[{level}] [Telegram] {message}")
        finally:
            db.close()

    def start(self):
        if not self.token:
            self.log("WARNING", "No TELEGRAM_BOT_TOKEN set in configuration. Telegram bot channel is OFFLINE.")
            return False
        
        self.running = True
        self.task = asyncio.create_task(self._poll_loop())
        self.log("INFO", "Telegram long polling worker started successfully. Bot is ONLINE.")
        return True

    def stop(self):
        self.running = False
        if self.task:
            self.task.cancel()
        self.log("INFO", "Telegram long polling worker stopped.")

    async def _poll_loop(self):
        async with httpx.AsyncClient() as client:
            while self.running:
                try:
                    url = f"{self.api_url}/getUpdates?offset={self.offset}&timeout=10"
                    response = await client.get(url, timeout=15.0)
                    
                    if response.status_code == 200:
                        data = response.json()
                        if data.get("ok"):
                            updates = data.get("result", [])
                            for update in updates:
                                # Update offset to avoid repeating updates
                                self.offset = update.get("update_id", 0) + 1
                                
                                # Process message
                                message = update.get("message", {})
                                await self._handle_message(message, client)
                    else:
                        self.log("ERROR", f"Error from Telegram API: status_code={response.status_code}")
                        await asyncio.sleep(10.0) # Wait before retry
                except httpx.RequestError as e:
                    # network failure/timeout is common with polling
                    await asyncio.sleep(5.0)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    self.log("ERROR", f"Unexpected error in polling loop: {e}")
                    await asyncio.sleep(5.0)

    async def _handle_message(self, message: dict, client: httpx.AsyncClient):
        chat = message.get("chat", {})
        chat_id = chat.get("id")
        user_name = chat.get("username") or chat.get("first_name") or f"User_{chat_id}"
        text = message.get("text")

        if not chat_id or not text:
            return

        self.log("INFO", f"Received message from '{user_name}' (ID: {chat_id}): '{text}'")

        # Save incoming Telegram message in DB
        db = SessionLocal()
        try:
            tg_msg_in = MessageModel(
                sender_type="channel",
                sender_id=f"telegram_{chat_id}",
                recipient_type="agent",
                recipient_id="triage",
                content=text
            )
            db.add(tg_msg_in)
            db.commit()
        finally:
            db.close()

        # Broadcast update to frontend UI
        await broadcast_ws({
            "type": "channel_message",
            "channel": "telegram",
            "sender": user_name,
            "content": text,
            "direction": "in"
        })

        # Send typing indicator to user to make the bot interactive
        await self._send_action(chat_id, "typing", client)

        # TRIGGER THE SMART SUPPORT WORKFLOW ASYNC
        self.log("INFO", f"Triggering 'template_support_gateway' workflow for query...")
        
        try:
            runner = WorkflowRunner("template_support_gateway")
            # Run workflow - triage processes request and executes logic
            final_response = await runner.execute(text, session_id=f"telegram_chat_{chat_id}")
            runner.close()
        except Exception as e:
            self.log("ERROR", f"Failed to run workflow for Telegram query: {e}")
            final_response = "Error: Sorry, I encountered an internal error while routing your request. Please try again."

        # Send final approved answer back to user via Telegram
        self.log("INFO", f"Sending response back to Telegram user '{user_name}': '{final_response[:50]}...'")
        await self._send_telegram_reply(chat_id, final_response, client)

        # Save outgoing message in DB
        db = SessionLocal()
        try:
            tg_msg_out = MessageModel(
                sender_type="agent",
                sender_id="supervisor",
                recipient_type="channel",
                recipient_id=f"telegram_{chat_id}",
                content=final_response
            )
            db.add(tg_msg_out)
            db.commit()
        finally:
            db.close()

        # Broadcast to Web UI chat tab
        await broadcast_ws({
            "type": "channel_message",
            "channel": "telegram",
            "sender": "Aether Supervisor",
            "content": final_response,
            "direction": "out"
        })

    async def _send_action(self, chat_id: int, action: str, client: httpx.AsyncClient):
        if not self.api_url:
            return
        try:
            url = f"{self.api_url}/sendChatAction"
            await client.post(url, json={"chat_id": chat_id, "action": action}, timeout=5.0)
        except Exception:
            pass

    async def _send_telegram_reply(self, chat_id: int, text: str, client: httpx.AsyncClient):
        if not self.api_url:
            return
        try:
            url = f"{self.api_url}/sendMessage"
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": "Markdown" # Standard formatting support
            }
            response = await client.post(url, json=payload, timeout=5.0)
            if response.status_code != 200:
                self.log("ERROR", f"Failed to reply on Telegram: {response.text}")
        except Exception as e:
            self.log("ERROR", f"HTTP network failure when replying to Telegram: {e}")

# Single global worker instance to be managed by FastAPI lifecycle
telegram_worker = TelegramBotWorker()

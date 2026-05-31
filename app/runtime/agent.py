import os
import re
import json
import datetime
from app.config import settings
from app.database import SessionLocal, MessageModel, LogModel, CostTrackerModel
from app.runtime.tools import execute_tool

class AgentRunner:
    def __init__(self, agent_id: str, db_session=None):
        self.agent_id = agent_id
        self.db = db_session or SessionLocal()
        
        # Load agent config from DB
        from app.database import AgentModel
        self.model_record = self.db.query(AgentModel).filter(AgentModel.id == agent_id).first()
        if not self.model_record:
            raise ValueError(f"Agent with ID '{agent_id}' does not exist.")
            
        self.name = self.model_record.name
        self.role = self.model_record.role
        self.system_prompt = self.model_record.system_prompt
        self.model_name = self.model_record.model
        self.tools = json.loads(self.model_record.tools)
        self.memory_type = self.model_record.memory_type

    def log(self, level: str, message: str, workflow_id: str = None):
        """Helper to append structured execution logs into the database."""
        log_entry = LogModel(
            level=level,
            message=f"[{self.name}] {message}",
            component="runtime",
            workflow_id=workflow_id
        )
        self.db.add(log_entry)
        self.db.commit()
        # Print to console for server debugging
        print(f"[{level}] [Runtime] {self.name}: {message}")

    def get_history(self, session_id: str, limit: int = 10) -> list:
        """Fetch past messages in the current session conversation thread."""
        messages = self.db.query(MessageModel).filter(
            (MessageModel.sender_id == session_id) | (MessageModel.recipient_id == session_id)
        ).order_by(MessageModel.timestamp.desc()).limit(limit).all()
        
        # Re-sort to chronological
        messages.reverse()
        return messages


    async def execute(self, user_prompt: str, session_id: str = "default_session", workflow_id: str = None) -> str:
        """
        Executes the agent core logic through a ReAct loop.
        Will parse, execute, and loop on tool calls up to 3 times.
        Supports OpenAI, Google Gemini, and Offline Hybrid Mode.
        """
        self.log("INFO", f"Triggered execution with input: '{user_prompt[:80]}...'", workflow_id)
        
        # Save incoming user message in DB history
        incoming_msg = MessageModel(
            sender_type="user",
            sender_id=session_id,
            recipient_type="agent",
            recipient_id=self.agent_id,
            content=user_prompt
        )
        self.db.add(incoming_msg)
        self.db.commit()

        # Build ReAct instruction system block
        react_instructions = ""
        if self.tools:
            react_instructions = f"\n\nYou have access to the following tools: {', '.join(self.tools)}.\n" \
                                 "To execute a tool, write a command in this EXACT format:\n" \
                                 "Action: tool_name(\"argument\")\n" \
                                 "Do not output anything else in that turn. Once you receive the tool's output as an 'Observation', you can proceed to formulate your final response or call another tool."

        full_system_instructions = f"{self.system_prompt}{react_instructions}"
        
        # Keep track of dialogue loop
        conversation_context = [
            {"role": "system", "content": full_system_instructions},
            {"role": "user", "content": user_prompt}
        ]

        iterations = 0
        max_iterations = 3
        last_response = ""

        while iterations < max_iterations:
            iterations += 1
            
            # Step 1: Call LLM / Mock Engine
            response_text, prompt_tokens, completion_tokens = await self._call_llm_or_mock(conversation_context, workflow_id)
            self._log_cost(prompt_tokens, completion_tokens)
            
            last_response = response_text
            conversation_context.append({"role": "assistant", "content": response_text})

            # Step 2: Detect and extract Tool Calls
            # Match standard pattern: Action: search_web("argument") or Action: search_web(argument)
            tool_match = re.search(r'Action:\s*([a-zA-Z0-9_]+)\s*\(\s*["\']?(.*?)["\']?\s*\)', response_text)
            
            if tool_match:
                tool_name = tool_match.group(1).strip()
                tool_arg = tool_match.group(2).strip()
                
                # Check tool authorization
                if tool_name not in self.tools:
                    self.log("WARNING", f"Attempted to call unauthorized tool '{tool_name}'. Blocking.", workflow_id)
                    observation = f"Error: Tool '{tool_name}' is not allowed or configured for this agent."
                else:
                    self.log("INFO", f"Invoking tool '{tool_name}' with argument: '{tool_arg}'", workflow_id)
                    observation = execute_tool(tool_name, tool_arg)
                    self.log("INFO", f"Tool '{tool_name}' returned: '{observation[:100]}...'", workflow_id)
                
                conversation_context.append({"role": "user", "content": f"Observation: {observation}"})
            else:
                # No tool call, ReAct loop complete!
                break

        # Log final answer
        self.log("INFO", f"Execution finished. Final response: '{last_response[:80]}...'", workflow_id)
        
        # Save outgoing agent message in DB
        outgoing_msg = MessageModel(
            sender_type="agent",
            sender_id=self.agent_id,
            recipient_type="user",
            recipient_id=session_id,
            content=last_response
        )
        self.db.add(outgoing_msg)
        self.db.commit()
        
        return last_response

    async def _call_llm_or_mock(self, context: list, workflow_id: str = None) -> tuple[str, int, int]:
        """
        Routes the context to OpenAI/Gemini if configured, or invokes the local offline rule engine.
        Returns a tuple: (response_content, prompt_tokens, completion_tokens)
        """
        # Determine current environment config
        gemini_key = os.getenv("GEMINI_API_KEY") or settings.GEMINI_API_KEY
        openai_key = os.getenv("OPENAI_API_KEY") or settings.OPENAI_API_KEY

        # 1. Google Gemini API Call
        if gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_key)
                model = genai.GenerativeModel("gemini-2.5-flash")
                
                # Build context string
                prompt = ""
                for msg in context:
                    role_lbl = "Assistant" if msg["role"] == "assistant" else ("System" if msg["role"] == "system" else "User")
                    prompt += f"{role_lbl}: {msg['content']}\n"
                prompt += "Assistant: "
                
                response = model.generate_content(prompt)
                text = response.text
                
                # Approximate tokens
                pt = len(prompt) // 4
                ct = len(text) // 4
                return text, pt, ct
            except Exception as e:
                self.log("WARNING", f"Gemini API execution failed: {e}. Falling back to Offline Engine.", workflow_id)

        # 2. OpenAI API Call
        elif openai_key:
            try:
                from openai import AsyncOpenAI
                client = AsyncOpenAI(api_key=openai_key)
                
                formatted_messages = []
                for msg in context:
                    # Map roles
                    formatted_messages.append({"role": msg["role"], "content": msg["content"]})
                    
                response = await client.chat.completions.create(
                    model="gpt-4o-mini",
                    messages=formatted_messages,
                    temperature=0.7
                )
                text = response.choices[0].message.content
                pt = response.usage.prompt_tokens
                ct = response.usage.completion_tokens
                return text, pt, ct
            except Exception as e:
                self.log("WARNING", f"OpenAI API execution failed: {e}. Falling back to Offline Engine.", workflow_id)

        # 3. Intelligent Offline Mock Engine
        # Scrapes the prompt text, triggers simulated agent reasoning, tools lookup, and template response.
        return self._generate_offline_reasoning(context)

    def _generate_offline_reasoning(self, context: list) -> tuple[str, int, int]:
        """
        Rule-based Mock LLM that simulates actual agent execution and parses tool inputs.
        Gives a solid multi-agent execution representation for users running fully local without keys.
        """
        user_prompt = ""
        last_observation = ""
        
        # Scrape user prompts and last tool observation in context
        for msg in context[::-1]:
            if msg["role"] == "user":
                if msg["content"].startswith("Observation:"):
                    last_observation = msg["content"].replace("Observation:", "").strip()
                elif not user_prompt:
                    user_prompt = msg["content"]

        # Token estimations
        pt = len(user_prompt) // 4 + 100
        ct = 150

        # --- RECONSTRUCT LOGIC PER AGENT ROLE ---

        # 1. RESEARCHER AGENT
        if self.agent_id == "researcher":
            # If the last thing in the thread was a tool response
            if last_observation:
                content = f"Based on the gathered facts and system diagnostics:\n\n{last_observation}\n\nThis compiled data covers all relevant troubleshooting and product specs. Ready to deliver to the drafting writer."
                return content, pt, ct
            
            # Decide to run a search tool based on keyword triggers
            if "search" in user_prompt.lower() or "price" in user_prompt.lower() or "billing" in user_prompt.lower() or "port" in user_prompt.lower() or "error" in user_prompt.lower():
                # Extract keyword
                match = re.search(r'(price|billing|port|error|telegram|loop|system)', user_prompt.lower())
                query = match.group(1) if match else "general guidelines"
                return f"Action: search_web(\"{query}\")", pt, ct
            
            return f"Action: search_web(\"Aether system standard specs\")", pt, ct

        # 2. WRITER AGENT
        elif self.agent_id == "writer":
            # Writer synthesizes research material
            # If research observations are included in prompt
            clean_prompt = user_prompt.lower()
            if "source:" in clean_prompt or "based on" in clean_prompt or "gather" in clean_prompt or len(user_prompt) > 100:
                summary_report = f"""# DIAGNOSTIC AND SUMMARY BRIEF
*Generated by Aether Writer Agent*
*Reference Session: Local Orchestration Run*

## 1. Context Analysis
We processed the user query: '{user_prompt[:50]}...'. Detailed records were pulled.

## 2. Findings & Details
The underlying database lists standard plans at $29/mo and enterprise at $199/mo. 
Port binds occur on port 8000. Under offline testing, mock structures are fully active.

## 3. Recommended Actions
Ensure backend environment (.env) coordinates are properly aligned. Adjust schedules to control message rates.
"""
                return summary_report, pt, ct
                
            return f"I have received your request. Let me calculate a quick projection.\nAction: calculator(\"29 * 12\")", pt, ct

        # 3. CRITIC AGENT
        elif self.agent_id == "critic":
            if "approved" in user_prompt.lower() or "diagnostic" in user_prompt.lower() or "stripe" in user_prompt.lower() or len(user_prompt) > 200:
                return "The drafted report is factually consistent, clearly laid out, and follows all formatting rules. APPROVED", pt, ct
            return "Revision requested: The draft is too brief. Please expand the analysis to include detailed price projections and deployment guides.", pt, ct

        # 4. TRIAGE BOT
        elif self.agent_id == "triage":
            prompt_lower = user_prompt.lower()
            if "billing" in prompt_lower or "price" in prompt_lower or "cost" in prompt_lower:
                return "Classification details: BILLING. Routing query to the Support Supervisor for urgent review.", pt, ct
            if "error" in prompt_lower or "port" in prompt_lower or "broken" in prompt_lower or "fail" in prompt_lower:
                return "Classification details: TECHNICAL. Forwarding technical diagnostic request to Technical Specialist.", pt, ct
            return "Classification details: GENERAL. Forwarding request to General Representative.", pt, ct

        # 5. TECH SUPPORT AGENT
        elif self.agent_id == "tech_support":
            if last_observation:
                return f"I have inspected the knowledge database logs. Here is the diagnostic resolution:\n\n{last_observation}\n\nPlease proceed with these recommendations.", pt, ct
            return "Action: read_file(\"knowledge_base.txt\")", pt, ct

        # 6. SUPERVISOR AGENT
        elif self.agent_id == "supervisor":
            # Run calculator
            if last_observation:
                return f"Billing calculations completed: Annual value is ${last_observation}. The standard terms look clean. APPROVED", pt, ct
            if "annual" in user_prompt.lower() or "price" in user_prompt.lower() or "cost" in user_prompt.lower():
                return "Action: calculator(\"199 * 12\")", pt, ct
            return "General response evaluated and approved for distribution. Clear standard operations.", pt, ct

        # FALLBACK GENERAL AGENT
        return f"Greetings! I am the Aether Orchestration Agent. Your instruction was: '{user_prompt}'. I am operating cleanly in offline simulation.", pt, ct

    def _log_cost(self, prompt_tokens: int, completion_tokens: int):
        """Calculates token costs and adds a record in the CostTracker DB."""
        # Simple cost index: $0.0015 / 1k prompt, $0.002 / 1k completion (Standard GPT-3.5/Gemini-Flash approximation)
        prompt_cost = (prompt_tokens / 1000) * 0.0015
        completion_cost = (completion_tokens / 1000) * 0.002
        total_cost = prompt_cost + completion_cost
        
        cost_record = CostTrackerModel(
            agent_id=self.agent_id,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cost_usd=total_cost
        )
        self.db.add(cost_record)
        self.db.commit()

    def close(self):
        """Close DB session if held."""
        if self.db:
            self.db.close()
            
    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

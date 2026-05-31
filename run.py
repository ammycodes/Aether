import os
import sys
import subprocess

def install_dependencies():
    print("=============================================================")
    print("      AETHER AGENT ORCHESTRATION PLATFORM - SETUP")
    print("=============================================================")
    print("Checking and installing necessary python packages...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])
        print("Dependency installation completed successfully.")
    except Exception as e:
        print(f"Warning: Failed to auto-install dependencies: {e}")
        print("Please make sure you run: pip install -r requirements.txt manually.")

def start_server():
    print("\n=============================================================")
    print("            BOOTING SERVER VIA UVICORN")
    print("=============================================================")
    
    # Load env for binding details
    from dotenv import load_dotenv
    load_dotenv()
    
    port = int(os.getenv("PORT", 8000))
    host = os.getenv("HOST", "127.0.0.1")
    
    import uvicorn
    # Start server
    uvicorn.run("app.main:app", host=host, port=port, reload=True)

if __name__ == "__main__":
    # 1. Install packages
    install_dependencies()
    
    # 2. Boot server
    start_server()

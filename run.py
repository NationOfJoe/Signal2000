"""Start the Signal2000 server: python run.py"""
import os

from signal2000 import create_app

app = create_app()

if __name__ == "__main__":
    app.run(
        host=os.environ.get("SIGNAL2000_HOST", "127.0.0.1"),
        port=int(os.environ.get("SIGNAL2000_PORT", "5000")),
    )

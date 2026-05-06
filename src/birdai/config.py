import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
BIRDAI_LOCATION = os.getenv("BIRDAI_LOCATION", "Zurich, Switzerland")
#!/usr/bin/env python
import os
import sys
import warnings
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

from sreeram_crew_scaffold.crew import SreeramCrewScaffold

warnings.filterwarnings("ignore", category=SyntaxWarning, module="pysbd")


def run():
    inputs = {
        "gold_channel_ids": os.getenv("GOLD_CHANNEL_IDS", ""),
        "silver_channel_ids": os.getenv("SILVER_CHANNEL_IDS", ""),
        "today_date": datetime.now().strftime("%B %d, %Y"),
    }
    try:
        SreeramCrewScaffold().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")


def train():
    inputs = {
        "gold_channel_ids": os.getenv("GOLD_CHANNEL_IDS", ""),
        "silver_channel_ids": os.getenv("SILVER_CHANNEL_IDS", ""),
        "today_date": datetime.now().strftime("%B %d, %Y"),
    }
    try:
        SreeramCrewScaffold().crew().train(
            n_iterations=int(sys.argv[1]), filename=sys.argv[2], inputs=inputs
        )
    except Exception as e:
        raise Exception(f"An error occurred while training the crew: {e}")


def replay():
    try:
        SreeramCrewScaffold().crew().replay(task_id=sys.argv[1])
    except Exception as e:
        raise Exception(f"An error occurred while replaying the crew: {e}")


def test():
    inputs = {
        "gold_channel_ids": os.getenv("GOLD_CHANNEL_IDS", ""),
        "silver_channel_ids": os.getenv("SILVER_CHANNEL_IDS", ""),
        "today_date": datetime.now().strftime("%B %d, %Y"),
    }
    try:
        SreeramCrewScaffold().crew().test(
            n_iterations=int(sys.argv[1]), eval_llm=sys.argv[2], inputs=inputs
        )
    except Exception as e:
        raise Exception(f"An error occurred while testing the crew: {e}")

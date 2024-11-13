import os

import sentry_sdk
from sentry_sdk import capture_exception
from parladata_base_api.storages.legislation_storage import LegislationConsideration
from parladata_base_api.storages.session_storage import Session
from parladata_base_api.storages.storage import DataStorage
from parladata_base_api.storages.vote_storage import Motion, Vote

from parlaparser.parse_legislation import LegislationParser
from parlaparser.parse_questions import QuestionParser
from parlaparser.parse_sessions import SessionParser
from parlaparser.parse_sifrant import MembershipsParser
from parlaparser.parse_votes_xml import VotesParser
from settings import (
    API_AUTH,
    API_URL,
    MAIN_ORG_ID,
    MANDATE,
    MANDATE_GOV_ID,
    MANDATE_STARTIME,
)

sentry_sdk.init(
    os.getenv("SENTRY_URL", None),
    environment=os.getenv("SENTRY_ENVIRONMENT", "test"),
    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0,
)


storage = DataStorage(
    MANDATE, MANDATE_STARTIME, MAIN_ORG_ID, API_URL, API_AUTH[0], API_AUTH[1]
)
storage.MANDATE_GOV_ID = MANDATE_GOV_ID
Motion.keys = ["datetime"]
Vote.keys = ["timestamp"]
LegislationConsideration.keys = [
    "timestamp",
    "legislation",
    "procedure_phase",
    "session",
]
try:
    parse_sifrant = MembershipsParser(storage)
    parse_sifrant.parse()
except Exception as e:
    capture_exception(e)

# session votes / speeches
try:
    session_parser = SessionParser(storage)
    session_parser.parse(parse_speeches=True, parse_votes=False)
except Exception as e:
    capture_exception(e)


try:
    session_parser = VotesParser(storage)
    session_parser.parse()
except Exception as e:
    capture_exception(e)

# use this for parse specific session
# session_parser.parse(session_number='69', session_type='Izredna', parse_speeches=True, parse_votes=True)

# # # questions
try:
    question_parser = QuestionParser(storage)
    question_parser.parse()
except Exception as e:
    capture_exception(e)

# Reload data storage for new session key for legislation
Session.keys = ["name", "organizations"]
storage = DataStorage(
    MANDATE, MANDATE_STARTIME, MAIN_ORG_ID, API_URL, API_AUTH[0], API_AUTH[1]
)
storage.MANDATE_GOV_ID = MANDATE_GOV_ID
# legislation
legislation_parser = LegislationParser(storage)
legislation_parser.parse()

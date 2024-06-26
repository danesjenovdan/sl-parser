from parlaparser.parse_sifrant import MembershipsParser
from parlaparser.parse_sessions import SessionParser
from parlaparser.parse_legislation import LegislationParser
from parlaparser.parse_questions import QuestionParser
from parlaparser.parse_votes_xml import VotesParser
from parlaparser.utils.storage.storage import DataStorage

import sentry_sdk
import os

sentry_sdk.init(
    os.getenv('SENTRY_URL', None),
    environment=os.getenv('SENTRY_ENVIRONMENT', 'test'),

    # Set traces_sample_rate to 1.0 to capture 100%
    # of transactions for performance monitoring.
    # We recommend adjusting this value in production.
    traces_sample_rate=1.0
)


storage = DataStorage()

parse_sifrant = MembershipsParser(storage)
parse_sifrant.parse()

# session votes / speeches
session_parser = SessionParser(storage)
session_parser.parse(parse_speeches=True, parse_votes=False)

session_parser = VotesParser(storage)
session_parser.parse()

# use this for parse specific session
# session_parser.parse(session_number='69', session_type='Izredna', parse_speeches=True, parse_votes=True)

# legislation
legislation_parser = LegislationParser(storage)
legislation_parser.parse()

# # questions
question_parser = QuestionParser(storage)
question_parser.parse()

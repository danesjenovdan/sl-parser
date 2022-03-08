from parlaparser.parse_sifrant import parse as parse_sifrant
from parlaparser.parse_sessions import SessionParser
from parlaparser.parse_legislation import LegislationParser
from parlaparser.parse_questions import QuestionParser
from parlaparser.utils.storage import DataStorage

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

#parse_sifrant(storage)

# session votes / speeches
session_parser = SessionParser(storage)
session_parser.parse(parse_speeches=True, parse_votes=False)

# use this for parse specific session
#session_parser.parse(session_number='66', session_type='Izredna', parse_speeches=True, parse_votes=False)

# legislation
# legislation_parser = LegislationParser(storage)
# legislation_parser.parse()

# # questions
# question_parser = QuestionParser(storage)
# question_parser.parse()

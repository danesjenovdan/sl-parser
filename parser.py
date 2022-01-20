from parlaparser.parse_sifrant import parse as parse_sifrant
from parlaparser.parse_sessions import SessionParser
from parlaparser.parse_legislation import LegislationParser
from parlaparser.parse_questions import QuestionParser
from parlaparser.utils.storage import DataStorage


storage = DataStorage()

#parse_sifrant(storage)

# session votes / speeches
session_parser = SessionParser(storage)
session_parser.parse(parse_speeches=True, parse_votes=True)

# use this for parse specific session
#session_parser.parse(session_number='52', session_type='Izredna')

# legislation
legislation_parser = LegislationParser(storage)
legislation_parser.parse()

# questions
question_parser = QuestionParser(storage)
question_parser.parse()

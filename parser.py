from parlaparser.parse_sifrant import parse as parse_sifrant
from parlaparser.utils.storage import DataStorage


storage = DataStorage()
parse_sifrant(storage)

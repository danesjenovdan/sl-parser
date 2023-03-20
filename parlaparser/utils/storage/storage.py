from parlaparser import settings
from parlaparser.utils.parladata_api import ParladataApi
from parlaparser.utils.storage.session_storage import SessionStorage
from parlaparser.utils.storage.legislation_storage import LegislationStorage
from parlaparser.utils.storage.question_storage import QuestionStorage
from parlaparser.utils.storage.people_storage import PeopleStorage
from parlaparser.utils.storage.organization_storage import OrganizationStorage
from parlaparser.utils.storage.agenda_item_storage import AgendaItemStorage
from parlaparser.utils.storage.membership_storage import MembershipStorage

from collections import defaultdict
from datetime import datetime

import logging
import editdistance


class NoneError(Exception):
    pass


class DataStorage(object):

    memberships = defaultdict(lambda: defaultdict(list))

    mandate_start_time = settings.MANDATE_STARTIME
    mandate_id = settings.MANDATE
    main_org_id = settings.MAIN_ORG_ID
    # old end

    def __init__(self):
        logging.warning(f'Start loading data')
        self.parladata_api = ParladataApi()

        self.session_storage = SessionStorage(self)
        self.legislation_storage = LegislationStorage(self)
        self.people_storage = PeopleStorage(self)
        self.organization_storage = OrganizationStorage(self)
        self.question_storage = QuestionStorage(self)
        self.agenda_item_storage = AgendaItemStorage(self)
        self.membership_storage = MembershipStorage(self)

    # area
    def set_area(self, data):
        added_area = self.parladata_api.set_area(data)
        return added_area.json()


    # links
    def set_link(self, data):
        added_link = self.parladata_api.set_link(data)
        return added_link


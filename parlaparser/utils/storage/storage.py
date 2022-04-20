from parlaparser import settings
from parlaparser.utils.parladata_api import ParladataApi
from parlaparser.utils.storage.session_storage import SessionStorage
from parlaparser.utils.storage.legislation_storage import LegislationStorage
from parlaparser.utils.storage.question_storage import QuestionStorage
from parlaparser.utils.storage.people_storage import PeopleStorage
from parlaparser.utils.storage.organization_storage import OrganizationStorage
from parlaparser.utils.storage.agenda_item_storage import AgendaItemStorage

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

        api_memberships = self.parladata_api.get_memberships()
        for membership in api_memberships:
            self.memberships[membership['organization']][membership['member']].append(membership)
        logging.warning(f'loaded {len(api_memberships)} memberships')


    # area

    def set_area(self, data):
        added_area = self.parladata_api.set_area(data)
        return added_area.json()


    # links

    def set_link(self, data):
        added_link = self.parladata_api.set_link(data)
        return added_link

    # memberships

    def patch_memberships(self, id, data):
        self.parladata_api.patch_memberships(id, data)

    def is_membership_parsed(self, person_id, org_id, role):
        if not org_id in self.memberships.keys():
            return False
        if not person_id in self.memberships[org_id].keys():
            return False
        for membership in self.memberships[org_id][person_id]:
            if membership['role'] == role:
                return True
        return False


    def get_membership_of_member_on_date(self, person_id, search_date, core_organization):
        memberships = self.memberships[core_organization]
        if person_id in memberships.keys():
            # person in member of parliamnet
            mems = memberships[person_id]
            for mem in mems:
                start_time = datetime.strptime(mem['start_time'], "%Y-%m-%dT%H:%M:%S")
                if start_time <= search_date:
                    if mem['end_time']:
                        end_time = datetime.strptime(mem['end_time'], "%Y-%m-%dT%H:%M:%S")
                        if end_time >= search_date:
                            return mem['on_behalf_of']
                    else:
                        return mem['on_behalf_of']
        return None

    def add_membership(self, data):
        membership = self.parladata_api.set_membership(data)
        if data['role'] == 'voter':
            logging.warning(membership)
            self.memberships[membership['organization']][membership['member']].append(membership)
        return membership

    def add_org_membership(self, data):
        membership = self.parladata_api.set_org_membership(data)
        return membership

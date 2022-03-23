from parlaparser import settings
from parlaparser.utils.parladata_api import ParladataApi
from parlaparser.utils.storage.session_storage import SessionStorage
from parlaparser.utils.storage.legislation_storage import LegislationStorage

from collections import defaultdict
from datetime import datetime

import logging
import editdistance


class NoneError(Exception):
    pass


class DataStorage(object):
    people = {}
    organizations = {}

    questions = {}

    agenda_items = {}
    memberships = defaultdict(lambda: defaultdict(list))

    mandate_start_time = settings.MANDATE_STARTIME
    mandate_id = settings.MANDATE
    main_org_id = settings.MAIN_ORG_ID
    # old end

    def __init__(self):
        logging.warning(f'Start loading data')
        self.parladata_api = ParladataApi()

        self.session_storage = SessionStorage(self)
        self.person_storage = None # TODO implement person storage


        for person in self.parladata_api.get_people():
            if not person['parser_names']:
                continue
            self.people[person['parser_names'].lower()] = person['id']
        logging.warning(f'loaded {len(self.people)} people')


        for org in self.parladata_api.get_organizations():
            if not org['parser_names']:
                continue
            self.organizations[org['parser_names'].lower()] = org['id']
        logging.warning(f'loaded {len(self.organizations)} organizations')

        # for item in self.parladata_api.get_agenda_items():
        #     self.agenda_items[self.get_agenda_key(item)] = item['id']
        # logging.warning(f'loaded {len(self.agenda_items)} agenda_items')

        # for question in self.parladata_api.get_questions():
        #     self.questions[self.get_question_key(question)] = {'id': question['id'], 'answer': question['answer_timestamp']}
        # logging.warning(f'loaded {len(self.questions)} questions')


        logging.debug(self.people.keys())
        api_memberships = self.parladata_api.get_memberships()
        for membership in api_memberships:
            self.memberships[membership['organization']][membership['member']].append(membership)
        logging.warning(f'loaded {len(api_memberships)} memberships')




    
    def get_id_by_parsername(self, object_type, name):
        """
        """
        try:
            name = name.lower()
        except:
            return None
        for parser_names in getattr(self, object_type).keys():
            for parser_name in parser_names.split('|'):
                if editdistance.eval(name, parser_name.lower()) == 0:
                    return getattr(self, object_type)[parser_names]
        return None

    def get_id_by_parsername_compare_rodilnik(self, object_type, name):
        """
        """
        cutted_name = [word[:-2] for word in name.lower().split(' ')]
        for parser_names in getattr(self, object_type).keys():
            for parser_name in parser_names.split('|'):
                cutted_parser_name = [word[:-2] for word in parser_name.lower().split(' ')]
                if len(cutted_parser_name) != len(cutted_name):
                    continue
                result = []
                for i, parted_parser_name in enumerate(cutted_parser_name):
                    result.append( parted_parser_name in cutted_name[i] )
                if result and all(result):
                    return getattr(self, object_type)[parser_names]
        return None

    def get_or_add_object_by_parsername(self, object_type, name, data_object, create_if_not_exist=True, name_type='normal'):
        if name_type == 'genitive':
            object_id = self.get_id_by_parsername_compare_rodilnik(object_type, name)
        else:
            object_id = self.get_id_by_parsername(object_type, name)
        added = False
        if not object_id:
            if not create_if_not_exist:
                return None, False
            if object_type == 'people':
                response = self.parladata_api.set_person(data_object)
            else:
                response = self.parladata_api.set_object(object_type, data_object)
            try:
                response_data = response.json()
                object_id = response_data['id']
                getattr(self, object_type)[response_data['parser_names'].lower()] = object_id
                added = True
            except Exception as e:
                raise Exception(f'Cannot add {object_type} {name} {response.json()} {e}')
                return None, False
        return object_id, added

    def get_or_add_person(self, name, data_object=None, name_type='normal'):
        if not data_object:
            data_object = {
                'name': name.strip().title(),
                'parser_names': name.strip()
            }
        return self.get_or_add_object_by_parsername('people', name, data_object, True, name_type=name_type)

    def get_person(self, name):
        return self.get_or_add_object_by_parsername('people', name, {}, False, name_type='normal')

    def add_person_parser_name(self, person_id, parser_name):
        person = self.parladata_api.add_person_parser_name(person_id, parser_name).json()
        self.people[person['parser_names'].lower()] = person['id']
        return person

    def get_or_add_organization(self, name, data_object):
        return self.get_or_add_object_by_parsername('organizations', name, data_object, True)


    # agenda items

    def get_or_add_agenda_item(self, data):
        logging.warning(self.get_agenda_key(data))
        logging.warning(self.agenda_items.keys())
        if self.get_agenda_key(data) in self.agenda_items.keys():
            return self.agenda_items[self.get_agenda_key(data)]
        else:
            added_agenda_item = self.parladata_api.set_agenda_item(data)
            return added_agenda_item['id']

    def get_agenda_key(self, agenda_item):
        return (agenda_item['name'] + '_' + agenda_item['datetime']).strip().lower()


    # area

    def set_area(self, data):
        added_area = self.parladata_api.set_area(data)
        return added_area.json()

    # questions

    def set_question(self, data):
        added_question = self.parladata_api.set_question(data)
        return added_question

    def check_if_question_is_parsed(self, question):
        key = self.get_question_key(question)
        return key in self.questions.keys()

    def get_question_key(self, question):
        return question['gov_id'].strip().lower()


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

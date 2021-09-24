from parlaparser import settings
from parlaparser.utils.parladata_api import ParladataApi

from collections import defaultdict
from datetime import datetime

import logging
import editdistance


class NoneError(Exception):
    pass


class DataStorage(object):
    people = {}
    organizations = {}
    votes = {}
    motions = {}
    sessions = {}
    sessions_with_speeches = []
    questions = {}
    legislation = {}
    acts = {}
    agenda_items = {}
    memberships = defaultdict(lambda: defaultdict(list))

    mandate_start_time = settings.MANDATE_STARTIME
    mandate_id = settings.MANDATE
    main_org_id = settings.MAIN_ORG_ID
    # old end

    def __init__(self):
        self.parladata_api = ParladataApi()
        for person in self.parladata_api.get_people():
            if not person['parser_names']:
                continue
            self.people[person['parser_names'].lower()] = person['id']
        logging.warning(f'loaded {len(self.people)} people')


        for org in self.parladata_api.get_organizations():
            if not org['parser_names']:
                continue
            self.organizations[org['parser_names'].lower()] = org['id']
            if org['classification'] == 'pg':
                pass
                # TODO od remove
                #self.klubovi[org['id']] = org['name']
        logging.warning(f'loaded {len(self.organizations)} organizations')
        for vote in self.parladata_api.get_votes():
            logging.warning(vote)
            self.votes[self.get_vote_key(vote)] = vote['id']
        logging.warning(f'loaded {len(self.votes)} votes')

        for session in self.parladata_api.get_sessions():
            self.sessions[f'{session["name"]}_{"_".join(list(map(str, session["organizations"])))}'] = session['id']
        logging.warning(f'loaded {len(self.sessions)} sessions')

        for session in self.sessions.values():
            speeches = self.parladata_api.get_speeches(session=session)
            if speeches:
                self.sessions_with_speeches.append(session)

        for motion in self.parladata_api.get_motions():
            self.motions[self.get_motion_key(motion)] = motion['id'] # TODO check if is key good key
        logging.warning(f'loaded {len(self.motions)} motions')

        for item in self.parladata_api.get_agenda_items():
            self.agenda_items[self.get_agenda_key(item)] = item['id']
        logging.warning(f'loaded {len(self.agenda_items)} agenda_items')

        for question in self.parladata_api.get_questions():
            self.questions[self.get_question_key(question)] = {'id': question['id'], 'answer': question['answer_timestamp']}
        logging.warning(f'loaded {len(self.questions)} questions')

        # for legislation in self.parladata_api.get_legislation():
        #     if legislation['classification'] == 'act':
        #         self.acts[legislation['text'].lower()] = {
        #             'id':legislation['id'],
        #             'ended':legislation['procedure_ended'],
        #             'procedure':legislation['procedure']
        #         }
        #     else:
        #         self.legislation[legislation['epa']] = {
        #             'id':legislation['id'],
        #             'ended':legislation['procedure_ended'],
        #             'procedure':legislation['procedure']
        #         }
        # logging.warning(f'loaded {len(self.acts)} acts')
        # logging.warning(f'loaded {len(self.legislation)} legislation')

    
        logging.debug(self.people.keys())
        api_memberships = self.parladata_api.get_memberships()
        for membership in api_memberships:
            self.memberships[membership['organization']][membership['member']].append(membership)
        logging.warning(f'loaded {len(api_memberships)} memberships')


    def get_vote_key(self, vote):
        if vote['name'] == None:
            raise NoneError
        return (vote['name']).strip().lower()

    def get_motion_key(self, motion):
        return (motion['datetime']).strip().lower()

    def get_question_key(self, question):
        return (question['title'] + question['timestamp']).strip().lower()

    def get_agenda_key(self, agenda_item):
        return (agenda_item['name'] + '_' + agenda_item['datetime']).strip().lower()

    def get_id_by_parsername(self, object_type, name):
        """
        """
        name = name.lower()
        for parser_names in getattr(self, object_type).keys():
            for parser_name in parser_names.split('|'):
                if editdistance.eval(name, parser_name) == 0:
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
                return None
            response = self.parladata_api.set_object(object_type, data_object)
            try:
                response_data = response.json()
                object_id = response_data['id']
                getattr(self, object_type)[response_data['parser_names'].lower()] = object_id
                added = True
            except:
                raise Exception(f'Cannot add {object_type} {name}')
                return None
        return object_id, added

    def get_or_add_person(self, name, data_object=None, name_type='normal'):
        if not data_object:
            data_object = {
                'name': name.strip().title(),
                'parser_names': name.strip()
            }
        return self.get_or_add_object_by_parsername('people', name, data_object, True, name_type=name_type)

    def get_or_add_organization(self, name, data_object):
        return self.get_or_add_object_by_parsername('organizations', name, data_object, True)

    def add_membership(self, data):
        membership = self.parladata_api.set_membership(data)
        if data['role'] == 'voter':
            logging.warning(membership)
            self.memberships[membership['organization']][membership['member']].append(membership)
        return membership

    def add_org_membership(self, data):
        membership = self.parladata_api.set_org_membership(data)
        return membership

    def add_or_get_session(self, data):
        key = f'{data["name"]}_{self.main_org_id}'
        if key in self.sessions:
            return self.sessions[key]
        else:
            data.update(mandate=self.mandate_id)
            session_data = self.parladata_api.set_session(data)
            self.sessions[key] = session_data['id']
            return session_data['id']

    def add_speeches(self, data):
        self.parladata_api.set_speeches(data)

    def set_ballots(self, data):
        added_ballots = self.parladata_api.set_ballots(data)

    def set_motion(self, data):
        added_motion = self.parladata_api.set_motion(data)
        return added_motion

    def get_or_add_agenda_item(self, data):
        logging.warning(self.get_agenda_key(data))
        logging.warning(self.agenda_items.keys())
        if self.get_agenda_key(data) in self.agenda_items.keys():
            return self.agenda_items[self.get_agenda_key(data)]
        else:
            added_agenda_item = self.parladata_api.set_agenda_item(data)
            return added_agenda_item['id']

    def check_if_motion_is_parsed(self, vote):
        key = self.get_motion_key(vote)
        return key in self.motions.keys()

    def check_if_question_is_parsed(self, question):
        key = self.get_question_key(question)
        return key in self.questions.keys()

    def set_vote(self, data):
        added_vote = self.parladata_api.set_vote(data)
        return added_vote

    def set_question(self, data):
        added_question = self.parladata_api.set_question(data)
        return added_question

    def set_link(self, data):
        added_link = self.parladata_api.set_link(data)
        return added_link

    def patch_motion(self, id, data):
        self.parladata_api.patch_motion(id, data)

    def patch_vote(self, id, data):
        self.parladata_api.patch_vote(id, data)

    def patch_memberships(self, id, data):
        self.parladata_api.patch_memberships(id, data)

    def set_legislation(self, data):
        added_legislation = self.parladata_api.set_legislation(data)
        return added_legislation

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

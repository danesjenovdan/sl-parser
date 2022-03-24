from parlaparser.utils.parladata_api import ParladataApi

import sentry_sdk


class Law(object):
    def __init__(self, id, epa, text, timestamp, uid, classification, is_new) -> None:
        self.id = id
        self.epa = epa
        self.text = text
        self.classification = classification
        self.timestamp = timestamp
        self.uid = uid
        self.is_new = is_new

    def get_key(self) -> str:
        return (self.epa).strip().lower()

    @classmethod
    def get_key_from_dict(ctl, data) -> str:
        return (data['epa'] if data['epa'] else '').strip().lower()


class ProcedurePhase(object):
    def __init__(self, id, name) -> None:
        self.id = id
        self.name = name

    def get_key(self) -> str:
        return (self.name if self.name else '').strip().lower()

    @classmethod
    def get_key_from_dict(ctl, data) -> str:
        return (data['name'] if data['name'] else '').strip().lower()


class LegislationStatuses(object):
    def __init__(self, id, name) -> None:
        self.id = id
        self.name = name

    def get_key(self) -> str:
        return (self.name if self.name else '').strip().lower()

    @classmethod
    def get_key_from_dict(ctl, data) -> str:
        return (data['name'] if data['name'] else '').strip().lower()


class LegislationClassification(object):
    def __init__(self, id, name) -> None:
        self.id = id
        self.name = name

    def get_key(self) -> str:
        return (self.name if self.name else '').strip().lower()

    @classmethod
    def get_key_from_dict(ctl, data) -> str:
        return (data['name'] if data['name'] else '').strip().lower()


class LegislationConsiceration(object):
    def __init__(self, id, law, timestamp, procedure_phase, session, is_new) -> None:
        self.id = id
        self.law = law
        self.timestamp = timestamp
        self.procedure_phase = procedure_phase
        self.session = session
        self.is_new = is_new

    def get_key(self) -> str:
        return f'{self.timestamp}_{self.law.id}_{self.procedure_phase.id}'

    @classmethod
    def get_key_from_dict(ctl, data) -> str:
        return f'{data["timestamp"]}_{data["legislation"]}_{data["procedure_phase"]}'


class LegislationStorage(object):
    def __init__(self, storage) -> None:
        self.parladata_api = ParladataApi()
        self.storage = storage

        self.legislation = {}
        self.legislation_by_id = {}
        self.legislation_classifications = {}
        self.legislation_statuses = {}
        self.procedure_phases = {}
        self.procedure_phases_by_id = {}
        self.legislation_considerations = {}

    def load_data(self):
        """
        load legislation if not loaded
        """
        if self.legislation:
            return
        print('Load legislation')
        for legislation_classification in self.parladata_api.get_legislation_classifications():
            classification = LegislationClassification(
                id=legislation_classification['id'],
                name=legislation_classification['name']
            )
            self.legislation_classifications[classification.get_key()] = classification

        for procedure_phase in self.parladata_api.get_procedure_phases():
            procedure_phase_obj = ProcedurePhase(
                id=procedure_phase['id'],
                name=procedure_phase['name']
            )
            self.procedure_phases[procedure_phase_obj.get_key()] = procedure_phase_obj
            self.procedure_phases_by_id[procedure_phase_obj.id] = procedure_phase_obj

        for legislation_status in self.parladata_api.get_legislation_statuses():
            status = LegislationStatuses(
                id=legislation_status['id'],
                name=legislation_status['name']
            )
            self.legislation_statuses[status.get_key()] = status

        for law in self.parladata_api.get_legislation():
            self.store_law(law, is_new=False)

        for legislation_consideration in self.parladata_api.get_legislation_consideration():
            self.store_legislation_consideration(legislation_consideration, is_new=False)

    def store_law(self, law_dict, is_new):
        law_obj = Law(
            id=law_dict['id'],
            epa=law_dict['epa'],
            text=law_dict['text'],
            timestamp=law_dict['timestamp'],
            classification=law_dict.get('classification', None),
            uid=law_dict['uid'],
            is_new=is_new
        )
        self.legislation[law_obj.get_key()] = law_obj
        self.legislation_by_id[law_obj.id] = law_obj
        return law_obj

    def store_legislation_consideration(self, consideration_dict, is_new):
        law = self.legislation_by_id[consideration_dict['legislation']]
        phase = self.procedure_phases_by_id[consideration_dict['procedure_phase']]
        consideration = LegislationConsiceration(
            id=consideration_dict['id'],
            law=law,
            timestamp=consideration_dict['timestamp'],
            procedure_phase=phase,
            session=consideration_dict['session'],
            is_new=is_new
        )
        self.legislation_considerations[consideration.get_key()] = consideration
        return consideration

    def set_law(self, data):
        added_law = self.parladata_api.set_legislation(data)
        law_obj = self.store_law(added_law, is_new=True)
        return law_obj


    def set_legislation_consideration(self, data):
        legislation_consideration = self.parladata_api.set_legislation_consideration(data).json()
        self.store_legislation_consideration(legislation_consideration, is_new=True)
        return legislation_consideration

    def patch_law(self, law, data):
        patched_law = self.parladata_api.patch_legislation(law.id, data)
        # check this if can produce memory leak
        law_obj = self.store_law(patched_law, is_new=False)
        return law_obj

    def is_law_parsed(self, epa):
        return epa in self.legislation.keys()

    def has_law_name(self, epa):
        return epa in self.legislation.keys()

    def update_or_add_law(self, law_data):
        epa = law_data['epa'].lower().strip()
        if epa in self.legislation.keys():
            law = self.legislation[epa]
            if law.text == None or law.text == '' or law.classification == None:
                law = self.patch_law(law, law_data)
        else:
            print(f'Adding new legislation with epa:{epa}!')
            law = self.set_law(law_data)
        return law

    def get_legislation_classifications_id(self, name):
        try:
            legislation_classifications = self.legislation_classifications.get(name)
        except:
            print(f'name is not in loaded legislation classifications')
            return
        return legislation_classifications.id

    def prepare_and_set_legislation_consideration(self, legislation_consideration):
        epa = legislation_consideration['epa'].lower().strip()
        if epa in self.legislation.keys():
            law = self.legislation[epa]
            phase_key = ProcedurePhase.get_key_from_dict({'name': legislation_consideration.pop('consideration_phase')})
            procedure_phase = self.procedure_phases.get(phase_key, None)
            if not procedure_phase:
                sentry_sdk.capture_message(f'There is new procedure phase {phase_key}')
                return

            organization_name = legislation_consideration['organization']
            if organization_name:
                organization_id, added = self.storage.get_or_add_organization(
                    organization_name,
                    {
                        'name': organization_name,
                        'parser_names': organization_name,
                    },
                )
            else:
                organization_id = None

            legislation_consideration.update({
                'organization': organization_id,
                'procedure_phase': procedure_phase.id,
                'legislation': law.id
            })
            legislation_consideration_key = LegislationConsiceration.get_key_from_dict(legislation_consideration)
            if not legislation_consideration_key in self.legislation_considerations.keys():
                legislation_consideration = self.set_legislation_consideration(
                    legislation_consideration
                )
            else:
                legislation_consideration = self.legislation_considerations[legislation_consideration_key]
            return legislation_consideration
        else:
            print('Legislation of this consideration is not parserd')

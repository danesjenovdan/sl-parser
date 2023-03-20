from parlaparser.utils.parladata_api import ParladataApi
import re


class Person(object):
    def __init__(self, name, id, parser_names, is_new) -> None:
        self.parladata_api = ParladataApi()

        # session members
        self.id = id
        self.name = name
        self.parser_names = parser_names
        self.is_new = is_new
        self.memberships = []

    def get_key(self) -> str:
        return self.parser_names.lower()

    @classmethod
    def get_key_from_dict(ctl, person) -> str:
        return person['parser_names'].lower()


class PeopleStorage(object):
    def __init__(self, core_storage) -> None:
        self.parladata_api = ParladataApi()
        self.people = {}
        self.people_by_id = {}
        self.storage = core_storage
        for person in self.parladata_api.get_people():
            self.store_person(person, is_new=False)

    def store_person(self, person, is_new) -> Person:
        temp_person = Person(
            name=person['name'],
            parser_names = person['parser_names'],
            id=person['id'],
            is_new=is_new,
        )
        self.people[temp_person.get_key()] = temp_person
        self.people_by_id[temp_person.id] = temp_person
        return temp_person

    def get_object_by_parsername(self, name):
        """
        """
        try:
            name = name.lower()
        except:
            return None
        for parser_names in self.people.keys():
            for parser_name in parser_names.split('|'):
                if name == parser_name:
                    return self.people[parser_names]
        return None

    def get_or_add_person(self, name, add=True) -> Person :
        prefix, name = self.get_prefix(name)
        # TODO save prefix
        person = self.get_object_by_parsername(name)
        if person:
            return person
        elif not add:
            return None
        data_object = {
            'name': name.strip().title(),
            'parser_names': name.strip()
        }
        response = self.parladata_api.set_person(data_object)
        response_data = response.json()
        return self.store_person(response_data, is_new=True)

    def get_or_add_person_object(self, person_data) -> Person:
        person = self.get_object_by_parsername(person_data['name'])
        if person:
            return person
        response = self.parladata_api.set_person(person_data)
        response_data = response.json()
        return self.store_person(response_data, is_new=True)

    def add_person_parser_name(self, person, parser_name):
        updated_person = self.parladata_api.add_person_parser_name(person.id, parser_name).json()
        new_person = self.store_person(updated_person, is_new=False)
        del self.people[person.parser_names.lower()]
        return new_person

    def get_person_by_id(self, id):
        return self.people_by_id.get(id, None)

    def get_prefix(self, name):
        prefix = re.findall('^[a-z]{0,4}\.', name)
        if prefix:
            prefix = prefix[0]
            return prefix, name.replace(prefix, '').strip()
        else:
            return None, name

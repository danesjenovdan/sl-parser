from parlaparser.utils.parladata_api import ParladataApi


class Organization(object):
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
    def get_key_from_dict(ctl, organization) -> str:
        return organization['parser_names'].lower()


class OrganizationStorage(object):
    def __init__(self, core_storage) -> None:
        self.parladata_api = ParladataApi()
        self.organizations = {}
        self.storage = core_storage
        self.organizations_by_id = {}
        for organization in self.parladata_api.get_organizations():
            if not organization['parser_names']:
                continue
            self.store_organization(organization, is_new=False)

    def store_organization(self, organization, is_new) -> Organization:
        temp_organization = Organization(
            name=organization['name'],
            parser_names = organization['parser_names'],
            id=organization['id'],
            is_new=is_new,
        )
        self.organizations[temp_organization.get_key()] = temp_organization
        self.organizations_by_id[temp_organization.id] = temp_organization
        return temp_organization

    def get_object_by_parsername(self, name):
        """
        """
        try:
            name = name.lower()
        except:
            return None
        for parser_names in self.organizations.keys():
            for parser_name in parser_names.split('|'):
                if name == parser_name:
                    return self.organizations[parser_names]
        return None

    def get_or_add_organization(self, name, add=True) -> Organization :
        organization = self.get_object_by_parsername(name)
        if organization:
            return organization
        elif not add:
            return None
        data_object = {
            'name': name.strip().title(),
            'parser_names': name.strip()
        }
        response = self.parladata_api.set_organization(data_object)
        response_data = response.json()
        return self.store_organization(response_data, is_new=True)

    def get_organization_by_id(self, id):
        return self.organizations_by_id.get(id, None)

    def get_or_add_organization_object(self, organization_data) -> Organization:
        organization = self.get_object_by_parsername(organization_data['name'])
        if organization:
            return organization
        response = self.parladata_api.set_organization(organization_data)
        response_data = response.json()
        return self.store_organization(response_data, is_new=True)

from parlaparser.utils.parladata_api import ParladataApi
from collections import defaultdict


class Membership(object):
    def __init__(self, person_id, organization_id, role, start_time, end_time, mandate, id, is_new) -> None:
        self.parladata_api = ParladataApi()

        # question members
        self.id = id
        self.person_id = person_id
        self.organization_id = organization_id
        self.role = role
        self.start_time = start_time
        self.end_time = end_time
        self.mandate = mandate
        self.is_new = is_new

    def get_key(self) -> str:
        return f'{self.person_id}_{self.organization_id}_{self.role}_{self.mandate}'

    @classmethod
    def get_key_from_dict(ctl, membership) -> str:
        return f'{membership["member"]}_{membership["organization"]}_{membership["role"]}_{membership["mandate"]}'

    def set_end_time(self):
        self.parladata_api.patch_memberships(self.id, {'end_time': self.end_time})


class MembershipStorage(object):
    def __init__(self, core_storage) -> None:
        self.parladata_api = ParladataApi()
        self.memberships = defaultdict(list)
        self.storage = core_storage

    def store_membership(self, membership, is_new) -> Membership:
        temp_membership = Membership(
            person_id=membership['member'],
            organization_id=membership['organization'],
            role=membership['role'],
            start_time=membership['start_time'],
            end_time=membership.get('end_time', None),
            mandate=membership['mandate'],
            id=membership['id'],
            is_new=is_new,
        )
        self.memberships[temp_membership.get_key()].append(temp_membership)
        person = self.storage.people_storage.get_person_by_id(membership['member'])
        organization = self.storage.organization_storage.get_organization_by_id(membership['organization'])
        if person:
            person.memberships.append(temp_membership)
        if organization:
            organization.memberships.append(temp_membership)
        return temp_membership

    def load_data(self):
        if not self.memberships:
            for membership in self.parladata_api.get_memberships(mandate=self.storage.mandate_id):
                self.store_membership(membership, is_new=False)
            print(f'laoded was {len(self.memberships)} memberships')

    def add_or_get_membership(self, data) -> Membership:
        key = Membership.get_key_from_dict(data)
        if key in self.memberships.keys():
            memberships = self.memberships[key]
            for membership in memberships:
                if not membership.end_time:
                    return membership

        membership = self.set_membership(data)
        new_membership = self.store_membership(membership, is_new=True)

        return new_membership

    def set_membership(self, data):
        added_membership = self.parladata_api.set_membership(data)
        return added_membership

    def check_if_membership_is_parsed(self, membership):
        key = Membership.get_key_from_dict(membership)
        return key in self.memberships.keys()


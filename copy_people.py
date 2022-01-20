import requests
import logging

from collections import defaultdict

from parlaparser.utils.storage import DataStorage

logger = logging.getLogger('logger')

BASE_URL = 'https://data.nov.parlameter.si/v1'

CLASSIFICATIONS = [
    'root',
    'pg',
    'commission',
    'committee',
    'council',
    'delegation',
    'friendship_group',
    'investigative_commission',
    'other',
]

def get_data_from_pager_api_gen(url, limit=300):
        end = False
        page = 1
        if '?' in url:
            url = url + f'&limit={limit}'
        else:
            url = url + f'?limit={limit}'
        logger.debug(url)
        while url:
            response = requests.get(url)
            if response.status_code != 200:
                logger.warning(response.content)
            data = response.json()
            yield data['results']
            url = data['next']

def get_objects(endpoint, limit=300, *args, **kwargs):
    url = f'{BASE_URL}/{endpoint}'
    return [
        obj
        for page in get_data_from_pager_api_gen(url, limit)
        for obj in page]

def role_mapper(role):
    return {
        'deputy': 'deputy',
        'member': 'member',
        'president': 'president',
        'vicepresident': 'deputy',
        'voter': 'voter',
        '\u010dlan': 'member'
    }[role]

def copy_old_data():
    storage = DataStorage()

    orgs_map_ids = {}
    people_map_ids = {}
    areas_map_ids = {}

    people_memberships = defaultdict(list)
    orgs = get_objects('organizations')
    for org in orgs:
        organization_id, added = storage.get_or_add_organization(
            org['name'],
            {
                'name': org['name'],
                'parser_names': '|'.join(org['name_parser'].split(',')) if org['name_parser'] else org['name'],
                'classification': org['classification'] if org['classification'] in CLASSIFICATIONS else 'other',
                'gov_id': org['gov_id'],
                'acronym': org['acronym'],
                'founding_date': org['founding_date'],
                'dissolution_date': org['dissolution_date'],
                'voters': org['voters'],
            },
        )
        orgs_map_ids[org['id']] = organization_id
        print('added org:', org['name'])

    # TODO copy links
    # TODO copy contact details

    areas = get_objects('areas')
    for area in areas:
        new_area_obj = storage.set_area({
            'name': area['name'],
            'classification': area['calssification'],
        })
        areas_map_ids[area['id']] = new_area_obj['id']
        print('added area:', area['name'])


    memberships = get_objects('memberships')
    for membership in memberships:
        # skip uncompelte data
        if not membership['person'] or not membership['organization'] or not membership['role']:
            continue

        people_memberships[membership['person']].append(membership)

    members_ids = people_memberships.keys()

    people = get_objects('persons')
    for person in people:
        if not person['id'] in members_ids:
            continue
        print(person)
        person_id, added_person = storage.get_or_add_person(
            person['name'],
            {
                'name': person['name'],
                'parser_names': '|'.join(person['name_parser'].split(',')),
                'classification': person['classification'],
                'date_of_birth': person['birth_date'].split('T')[0] if person['birth_date'] else None,
                'date_of_death': person['death_date'].split('T')[0] if person['death_date'] else None,
                'districts': [areas_map_ids[area_id] for area_id in person['districts']],

            },
        )

        print('added person:', person['name'])
        for membership in people_memberships[person['id']]:
            storage.add_membership(
                {
                    'member': person_id,
                    'organization': orgs_map_ids[membership['organization']],
                    'on_behalf_of': orgs_map_ids[membership['on_behalf_of']] if membership['on_behalf_of'] else None,
                    'start_time': membership['start_time'],
                    'end_time': membership['end_time'],
                    'role':  role_mapper(membership['role']),
                }
            )



if __name__ == "__main__":
    copy_old_data()

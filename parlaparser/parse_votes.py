import requests
from lxml import html
from enum import Enum
from urllib import parse
from datetime import datetime
import sentry_sdk

from parlaparser.settings import BASE_URL

class VotesParser(object):
    def __init__(self, storage, session):
        self.session = session
        self.storage = storage
        self.session.load_votes()
        self.storage.legislation_storage.load_data()

    def parse_votes(self, request_session, htree):
        lines = htree.cssselect('form>div>table>tbody>tr')
        for line in lines:
            columns = line.cssselect('td')
            # if there's not date for vote, skip it
            if not columns[0].cssselect('span') or not columns[0].cssselect('span')[0].text:
                continue
            date = columns[0].cssselect('span')[0].text
            print(date)
            time = columns[1].cssselect('span')[0].text
            if columns[3].cssselect('span'):
                epa = columns[3].cssselect('span')[0].text
            else:
                epa = ''
            url_text = columns[4].cssselect('span')[0].text
            ballots_url = columns[4].cssselect('a')[0].get('href')
            uid = parse.parse_qs(parse.urlsplit(ballots_url).query)['uid'][0]


            if self.session.vote_storage.check_if_motion_is_parsed({'gov_id': uid}):
                print('this vote is already parsed')
                continue

            parsed_ballots = self.parse_ballots(ballots_url)

            try:
                start_time = datetime.strptime(f'{date} {time}', '%d. %m. %Y %X')
            except Exception as e:
                # TODO send sentry error
                print('parse date error', e)
                continue

            motion_meta = parsed_ballots['meta']
            if motion_meta['title']:
                title = f'{motion_meta["title"]} - {motion_meta["doc_name"]}'
            else:
                title = motion_meta["doc_name"]

            # dont parse motion without title
            if not title:
                continue

            legislation_id = None
            if epa:
                if self.storage.legislation_storage.is_law_parsed(epa):
                    legislation_id = self.storage.legislation_storage.legislation[epa].id
                else:
                    legislation = self.storage.legislation_storage.set_law({
                        'epa': epa
                    })
                    legislation_id = legislation.id

            motion = {
                'title': title,
                'text': title,
                'datetime': start_time.isoformat(),
                'session': self.session.id,
                'gov_id': uid
            }
            if legislation_id:
                motion['law'] = legislation_id
            vote = {
                'name': title,
                'timestamp': start_time.isoformat(),
                'session': self.session.id,
            }
            motion_obj = self.session.vote_storage.set_motion(motion)
            try:
                motion_id = motion_obj.id
            except Exception as e:
                # skip adding vote because adding motion was fail
                sentry_sdk.capture_exception(e)
                continue
            vote['motion'] = motion_id
            vote_obj = self.session.vote_storage.set_vote(vote)
            vote_id = int(vote_obj['id'])

            self.save_ballots(parsed_ballots['ballots'], vote_id)

            # TODO add links to votes...
            # for link in data['links']:
            #     # save links
            #     link_data = {
            #         'motion': motion_id,
            #         #'agenda_item': self.agenda_item_id,
            #         'url': link['url'],
            #         'name': link['title'],
            #         'tags': [link['tag']]
            #     }
            #     if 'law' in motion.keys():
            #         link_data.update({'law': motion['law']})
            #     self.storage.set_link(link_data)

        # follow pagination
        try:
            paging_meta = htree.cssselect(".pagerDeluxe_text")[0].text.split(' ')
        except:
            # This exit method if session has not votes
            return
        current_page = paging_meta[1]
        last_page = paging_meta[3]
        if int(current_page) < int(last_page):
            post_url = htree.cssselect('form')[0].get('action')
            form_id = htree.cssselect('form')[0].get('id')
            view_state = htree.cssselect('input[name="javax.faces.ViewState"]')[0].get('value')
            url_encode = htree.cssselect('input[name="javax.faces.encodedURL"]')[0].get('value')

            url = f'{BASE_URL}{post_url}'
            payload = {
                'vax.faces.encodedURL': url_encode,
                f'{form_id}_SUBMIT': 1,
                f'{form_id}:tableEx1:goto1__pagerGoText': 2,
                'javax.faces.ViewState': view_state,
                f'{form_id}:tableEx1:deluxe1__pagerNext.x': 0,
                f'{form_id}:tableEx1:deluxe1__pagerNext.y': 0,
            }

            response = request_session.post(url, data=payload)
            session_htree = html.fromstring(response.content)
            self.parse_votes(request_session, session_htree)



    def parse_ballots(self, url):
        output = {
            'ballots': [],
            'meta': {}
        }
        ballots_content = requests.get(url=f'{BASE_URL}{url}').content
        htree = html.fromstring(ballots_content)
        body = htree.cssselect('.stControlBody')[0]
        tables = body.cssselect('table')
        header = tables[0]
        content = tables[1]
        title = ''
        document_name = ''
        # parse header
        for tr in header.cssselect('tbody>tr'):
            tds = tr.cssselect('td')
            span_b = tds[0].cssselect('span>b')
            if not span_b:
                continue
            key = span_b[0].text
            value = tds[1]
            if key == 'Dokument':
                span = value.cssselect('span')
                if not span:
                    continue
                document_name = span[0].text
            if key == 'Naslov':
                em = value.cssselect('span>em')
                if not em:
                    continue
                title = em[0].text
        output['meta'] = {
            'title': title,
            'doc_name': document_name,
        }

        # parse content
        for tr in content.cssselect('tr')[1:]:
            tds = tr.cssselect('td')
            output['ballots'].append({
                'voter': tds[0].text,
                'kvorum': tds[1].text,
                'option': tds[2].text,
            })

        return output

    def save_ballots(self, ballots, vote_id):
        ballots_for_save = []
        for ballot in ballots:
            person_id, added_person = self.storage.get_or_add_person(
                ballot['voter']
            )
            person_option = ''
            kvorum = ballot['kvorum']
            option = ballot['option']
            if not kvorum:
                person_option = 'absent'
            elif option == 'Ni':
                person_option = 'abstain'
            elif option == 'Proti':
                person_option = 'against'
            elif option == 'Za':
                person_option = 'for'
            else:
                raise Exception('Unkonwn option')
            ballots_for_save.append({
                'personvoter': person_id,
                'option': person_option,
                'vote': vote_id
            })
        self.session.vote_storage.set_ballots(ballots_for_save)

import requests
from requests_ntlm import HttpNtlmAuth
from bs4 import BeautifulSoup
import json
import os
from dotenv import load_dotenv

load_dotenv()

USERNAME = 'GUC\\abdelrahman.mourad'
PASSWORD = os.environ.get('CMS_PASSWORD')  # set with: export CMS_PASSWORD='yourpassword'
SEEN_FILE = 'seen.json'
NTFY_TOPIC = 'guc-cms-abdo-8f2k1x'  # your actual topic

session = requests.Session()
session.auth = HttpNtlmAuth(USERNAME, PASSWORD)


def get_homepage_soup():
    r = session.get('https://cms.guc.edu.eg/apps/student/HomePageStn.aspx')
    return BeautifulSoup(r.text, 'html.parser')


def get_courses_and_season(soup):
    """Returns (season_id, [(course_id, course_name), ...])."""
    table = soup.select_one('table#ContentPlaceHolderright_ContentPlaceHoldercontent_GridViewcourses')
    courses = []
    season_id = None
    if table is None:
        print("Courses table not found — page structure may have changed")
        return season_id, courses
    for row in table.select('tr')[1:]:  # skip header row
        cells = row.select('td')
        if len(cells) >= 6:
            course_name = cells[1].text.strip()   # 2nd column = Name
            course_id = cells[4].text.strip()      # 5th column = ID
            season_id = cells[5].text.strip()      # 6th column = SeasonId
            courses.append((course_id, course_name))
    return season_id, courses


def load_seen():
    if os.path.exists(SEEN_FILE):
        with open(SEEN_FILE) as f:
            return json.load(f)
    return {}


def save_seen(seen):
    with open(SEEN_FILE, 'w') as f:
        json.dump(seen, f)


def notify(message):
    requests.post(
        f'https://ntfy.sh/{NTFY_TOPIC}',
        data=message.encode('utf-8'),
        headers={'Title': 'GUC CMS Update', 'Priority': 'high'}
    )


def get_current_items(course_id, season_id):
    """Returns a dict of {content_id: content_title}."""
    r = session.get(f'https://cms.guc.edu.eg/apps/student/CourseViewStn.aspx?id={course_id}&sid={season_id}')
    soup = BeautifulSoup(r.text, 'html.parser')
    current_items = {}
    for week in soup.select('.weeksdata'):
        for content in week.select('.card-body'):
            content_id_div = content.select_one('div[id^="content"]')
            if content_id_div:
                content_id = content_id_div['id']
                # the title sits in the very next <div> after the id div
                title_div = content_id_div.find_next_sibling('div')
                title = title_div.get_text(strip=True) if title_div else content_id
                current_items[content_id] = title
    return current_items


def main():
    if not PASSWORD:
        print("CMS_PASSWORD environment variable not set")
        return

    seen = load_seen()
    soup = get_homepage_soup()

    season_id, courses = get_courses_and_season(soup)
    if not season_id or not courses:
        print("Could not find season ID / courses — page structure may have changed")
        return

    print(f"Season {season_id} — found {len(courses)} courses: {[c[0] for c in courses]}")

    for course_id, course_name in courses:
        course_id = str(course_id)
        current_items = get_current_items(course_id, season_id)  # {id: title}
        old_ids = set(seen.get(course_id, {}).keys()) if isinstance(seen.get(course_id), dict) else set(seen.get(course_id, []))
        new_ids = set(current_items.keys()) - old_ids

        if new_ids:
            new_titles = [current_items[i] for i in new_ids]
            titles_text = "\n".join(f"- {t}" for t in new_titles)
            notify(f"{course_name}\n{titles_text}")

        seen[course_id] = current_items  # store as {id: title} dict now

    save_seen(seen)


if __name__ == '__main__':
    main()
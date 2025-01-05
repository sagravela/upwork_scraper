from DrissionPage import ChromiumPage, ChromiumOptions
from dotenv import load_dotenv
from pydantic import BaseModel
from urllib3.util import parse_url
import os, csv, logging, math
import argparse, re
from bs4 import BeautifulSoup

class UpworkOffer(BaseModel):
    title: str
    connections: int
    posted_at: str
    proposals: str = 0
    last_viewed_by_client: str = None
    interviewing: int = None
    invites_sent: int = 0
    unanswered_invites: int = invites_sent
    description: str
    link: str


def setup():
    "Set up Crhromium and their options."
    print("Setting up Chromium...")
    options = ChromiumOptions().set_browser_path('/usr/bin/brave-browser')#.headless()
    driver = ChromiumPage(addr_or_opts=options).latest_tab
    return driver

def login(url: str, username: str, password: str):
    "Login to Upwork and wait for js be rendered."
    print(f"Login as {username} in {url} ...")
    driver.get(url)
    driver.ele('#login_username').input(username)
    driver.ele('#login_password_continue').click()
    driver.ele('#login_password').input(password)
    driver.ele('#login_control_continue').click()
    driver.wait(5)

    print("Login Succesful")

def scrape_data(url):
    "Scrape proposals from Upwork, parse and save them."
    print("Requesting page: " + url)
    # Request the page
    driver.get(url)
    soup = BeautifulSoup(driver.html, 'html.parser')

    # Get the offers
    offers = []
    anchor_tags = soup.select('.job-tile-title a')
    for anchor in anchor_tags:
        try:
            offer_data = {}
            # Offer title
            offer_data['title'] = anchor.get_text()
            # Offer link
            offer_data['link'] = "https://www.upwork.com" + anchor.get('href')
            # Get the offer data
            print("Requesting offer: " + offer_data['link'])
            driver.get(offer_data['link'])
            soup = BeautifulSoup(driver.html, 'html.parser')
            # Data is along sections
            sections = [s.get_text() for s in soup.select('.air3-card-section')]
            # Posted time
            offer_data['posted_at'] = re.search(r'Posted\n(.*)ago', sections[0]).group(1).strip()
            # Connections number
            offer_data['connections'] = int(re.findall(r'\d+', sections[0])[1])
            # Second section is the description
            offer_data['description'] = sections[1].strip()
            # Metadata
            client_data = soup.select_one('ul.client-activity-items')
            keys = [k.get_text().strip().replace(' ', '_').lower()[:-1] for k in client_data.select('span.title')]
            values = [v.get_text().strip() for v in client_data.select('span.value') + client_data.select('div.value')]
            offer_data.update(zip(keys, values))
            offer = UpworkOffer(**offer_data)
            offers.append(offer.model_dump())
            print(f"Offer scraped:\n{offer}")
        except Exception as e:
            print(e)
    return offers

def main():
    global driver

    load_dotenv()
    username = os.environ.get('UPWORK_USERNAME')
    password = os.environ.get('UPWORK_PASSWORD')
    parser = argparse.ArgumentParser(description='Scrape Upwork job offers.')
    parser.add_argument('-l', '--limit', type=int, default=100, help='Limit of job offers to scrape')
    parser.add_argument('-q', '--query', type=str, default='data science', help='Search query for job offers')
    args = parser.parse_args()

    try:
        driver = setup()
        login('https://www.upwork.com/ab/account-security/login', username, password)

        # Scrape links for each page until limit.
        data = []
        for i in range(1, math.ceil(args.limit / 10) + 1):
            page_url = parse_url(f'https://www.upwork.com/nx/search/jobs/?q={args.query}').url
            # add page number after the first page
            if i > 1:
                page_url += f"&page={i}"
            data.append(scrape_data(page_url))

        # Save data to CSV
        flattened_data = [item for sublist in data for item in sublist]
        with open(f'{args.query}.csv', mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(UpworkOffer.model_fields.keys()))
            writer.writeheader()
            writer.writerows(flattened_data)
        print(f"Saved {len(flattened_data)} offers to {args.query.replace(' ', '-')}.csv")
    except Exception as e:
        print(e)
        driver.close()
    finally:
        driver.close()

if __name__ == '__main__':
    main()
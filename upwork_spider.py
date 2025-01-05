from DrissionPage import ChromiumPage, ChromiumOptions
from dotenv import load_dotenv
from pydantic import BaseModel
from urllib3.util import parse_url
import os, csv, logging, math
import argparse, re
from bs4 import BeautifulSoup
from datetime import datetime, timedelta

class UpworkOffer(BaseModel):
    "Data Validator"
    title: str
    connections: int
    posted_at: datetime
    proposals: str = 0
    last_viewed_by_client: datetime = None
    interviewing: int = None
    invites_sent: int = 0
    unanswered_invites: int = invites_sent
    description: str
    link: str

def setup():
    "Set up Crhromium and their options."
    logging.info("Setting up Chromium...")
    # Cloudflare server detects as bot when runned as headless mode
    options = ChromiumOptions().set_browser_path('/usr/bin/brave-browser')#.headless()
    driver = ChromiumPage(addr_or_opts=options).latest_tab
    return driver

def login(url: str, username: str, password: str):
    "Login to Upwork and wait for js be rendered."
    logging.info(f"Login as {username} in {url} ...")
    driver.get(url)
    driver.ele('#login_username').input(username)
    driver.ele('#login_password_continue').click()
    driver.ele('#login_password').input(password)
    driver.ele('#login_control_continue').click()
    driver.wait(5)

    logging.info("Login successful.")

def scrape_data(url):
    "Scrape proposals from Upwork, parse and save them."
    logging.info("Requesting page: " + url)
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
            logging.info("Requesting offer: " + offer_data['link'])
            driver.get(offer_data['link'])
            soup = BeautifulSoup(driver.html, 'html.parser')
            # Data is along sections
            sections = [s.get_text() for s in soup.select('.air3-card-section')]
            # Posted time
            posted_at = re.search(r'Posted\n(.*)ago', sections[0]).group(1).strip()
            offer_data['posted_at'] = parse_datetime(posted_at)
            # Connections number
            offer_data['connections'] = int(re.findall(r'\d+', sections[0])[1])
            # Second section is the description
            offer_data['description'] = sections[1].strip()
            # Metadata
            client_data = soup.select_one('ul.client-activity-items')
            keys = [k.get_text().strip().replace(' ', '_').lower()[:-1] for k in client_data.select('span.title')]
            values = [v.get_text().strip() for v in client_data.select('span.value') + client_data.select('div.value')]
            offer_data.update(zip(keys, values))

            # Parse last viewed by the client to datetime
            if 'last_viewed_by_client' in offer_data.keys():
                offer_data['last_viewed_by_client'] = parse_datetime(offer_data['last_viewed_by_client'])
            # Validate data
            offer = UpworkOffer(**offer_data)
            offers.append(offer.model_dump())
            logging.info(f"Offer scraped:\n{offer}")
        except Exception as e:
            logging.error(e)
    return offers

def parse_datetime(date: str) -> datetime:
    now = datetime.now()
    splits = date.split()
    number, unit = splits[0], splits[1]
    number = int(number)
    
    if 'second' in unit:
        delta = timedelta(seconds=number)
    elif 'minute' in unit:
        delta = timedelta(minutes=number)
    elif 'hour' in unit:
        delta = timedelta(hours=number)
    elif 'day' in unit:
        delta = timedelta(days=number)
    elif 'week' in unit:
        delta = timedelta(weeks=number)
    else:
        raise ValueError(f"Unknown time unit: {unit}")
    
    return (now - delta).strftime('%Y-%m-%d %H:%M:%S')

def main():
    global driver

    load_dotenv()
    # Configure logging
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
    parser = argparse.ArgumentParser(description='Scrape Upwork job offers.')
    parser.add_argument('-l', '--limit', type=int, default=100, help='Limit of job offers to scrape')
    parser.add_argument('-q', '--query', type=str, default='data science', help='Search query for job offers')
    parser.add_argument('-u', '--username', type=str, default=os.environ.get('UPWORK_USERNAME'), help="Upwork username or e-mail")
    parser.add_argument('-p', '--password', type=str, default=os.environ.get('UPWORK_PASSWORD'), help="Upwork password")
    args = parser.parse_args()
    try:
        driver = setup()
    except Exception as e:
        logging.error(e)

    try:
        login('https://www.upwork.com/ab/account-security/login', args.username, args.password)
    except Exception as e:
        driver.close()
        logging.error(f"Couldn't Login: {e}")
        logging.info("Driver closed.")

    try:        
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
        filename = args.query.replace(' ', '-')
        with open(f'{filename}.csv', mode='w', newline='') as file:
            writer = csv.DictWriter(file, fieldnames=list(UpworkOffer.model_fields.keys()))
            writer.writeheader()
            writer.writerows(flattened_data)
        logging.info(f"Saved {len(flattened_data)} offers to {args.query.replace(' ', '-')}.csv")
    except Exception as e:
        logging.error(e)
        driver.close()
    finally:
        driver.close()
        logging.info("Driver closed.")

if __name__ == '__main__':
    main()
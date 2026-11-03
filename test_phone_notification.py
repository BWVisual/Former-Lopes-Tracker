#!/usr/bin/env python3
"""Send ONE opt-in Telegram test alert; no game results or dedupe state changed."""
import os
import sys
import requests


def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '').strip()
    chat_id = os.environ.get('TELEGRAM_CHAT_ID', '').strip()
    if not (token and chat_id):
        sys.exit('Configure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID first (never paste them into the repo).')
    r = requests.post(
        f'https://api.telegram.org/bot{token}/sendMessage',
        json={
            'chat_id':chat_id,
            'text':'🏀 Lopes Tracker test\nYour individual game alerts are connected. This is a test, not a real box score.',
            'disable_web_page_preview':True,
        }, timeout=20,
    )
    r.raise_for_status()
    if not r.json().get('ok'):
        sys.exit('Telegram reported an error while sending the test.')
    print('Telegram accepted the test message. Check your phone and make sure notifications are enabled for this chat.')


if __name__ == '__main__':
    main()

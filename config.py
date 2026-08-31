import os

from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
# Chat where every upload lands for moderation (bot must be admin there).
ADMIN_CHAT_ID: int = int(os.getenv("ADMIN_CHAT_ID", "0"))
# Complaints go here instead, when set — otherwise they join the moderation chat.
REPORTS_CHAT: str = os.getenv("REPORTS_CHAT", "")
# Author profiles awaiting review; empty falls back to the moderation chat too.
PROFILES_CHAT: str = os.getenv("PROFILES_CHAT", "")
# Circles awaiting review; empty means ADMIN_CHAT_ID.
CIRCLES_CHAT: str = os.getenv("CIRCLES_CHAT", "")
# Personal ids allowed to run /stats and /refund.
ADMIN_IDS: set[int] = {
    int(x) for x in os.getenv("ADMIN_IDS", "").replace(" ", "").split(",") if x
}
DB_PATH: str = os.getenv("DB_PATH", "bot.db")
# Custom emoji need a Premium owner or Fragment usernames; set to 0 to fall back
# to plain unicode everywhere.
PREMIUM_EMOJI: bool = os.getenv("PREMIUM_EMOJI", "1") not in ("0", "false", "False")

# --- crypto payments -----------------------------------------------------
# Keys come from the payment bots themselves: @CryptoBot → Crypto Pay → Create
# App, @tonRocketBot → Rocket Pay → Create App. An empty key simply hides that
# method from the checkout, so the bot runs fine without either of them.
CRYPTOBOT_TOKEN: str = os.getenv("CRYPTOBOT_TOKEN", "")
CRYPTOBOT_API: str = os.getenv("CRYPTOBOT_API", "https://pay.crypt.bot/api")
# --- card payments through ParityPay -------------------------------------
# Two values from the shop's settings in the ParityPay dashboard: the shop UUID
# and secret key №1. Key №2 signs their webhooks and is not needed here — the
# bot polls its own invoices, same as it does with crypto.
PARITYPAY_SHOP_ID: str = os.getenv("PARITYPAY_SHOP_ID", "")
PARITYPAY_SECRET: str = os.getenv("PARITYPAY_SECRET", "")
PARITYPAY_API: str = os.getenv("PARITYPAY_API", "https://api.paritypay.net")

XROCKET_KEY: str = os.getenv("XROCKET_KEY", "")
XROCKET_API: str = os.getenv("XROCKET_API", "https://pay.xrocket.exchange")
# Pay API v2: a separate service with its own credentials, and the one the bot
# hands out tokens for now. Which of the two a key belongs to is worked out from
# the key itself — see crypto._xrocket_flavour.
XROCKET_API_V2: str = os.getenv("XROCKET_API_V2", "https://pay.api.xrocket.exchange")

# --- BotStat: broadcasts through @BotManRobot, audience check in @BotSafeRobot
# Access key: https://botstat.io/dashboard (раздел API). Without it only the
# BotMan upload works — it authenticates by the bot token alone.
BOTSTAT_KEY: str = os.getenv("BOTSTAT_KEY", "")
BOTSTAT_API: str = os.getenv("BOTSTAT_API", "https://api.botstat.io")

# Nothing here is exposed to the internet, so a webhook has nowhere to land —
# the bot asks the provider about its own invoices instead.
INVOICE_TTL = 1800  # seconds an invoice stays payable
INVOICE_POLL = 10.0  # seconds between status checks
INVOICE_TIMEOUT = 15.0  # seconds to wait for a provider's answer

# --- economy ---
WATCH_COST = 2
# Uploading pays nothing: a circle is a shop window for the author's profile,
# and the only way to earn coins is selling access to it.
REWARD = {"f": 0, "m": 0}
MIN_DURATION = 8  # seconds; anything shorter is refused
STAR_COST = 2  # stars for one coin
MIN_STARS = 20
MAX_STARS = 100_000
MAX_PENDING = 5  # unmoderated uploads a user may hold at once
WATCH_COOLDOWN = 1.0  # seconds between "watch" taps

STAR_PACKS = (20, 50, 100, 250)
WELCOME_BONUS = 6  # coins handed to a newcomer, enough for a few circles
# The first circle arrives on its own, right after the rules are accepted:
# a newcomer who has to find the button first often never sees one.
WELCOME_CIRCLE = 1
SUB_BONUS = 4  # paid once, when the channel subscription is first confirmed
REF_REWARD = 3  # coins for a referral that made it through the subscription gate
VIEW_PAYOUT = 0  # views and likes buy reach, not coins
LIKE_BONUS = 0
LIKE_BOOST = 1  # how much one net like weighs when picking what to show
# --- re-engagement pushes ---
PUSH_ENABLED = 1
PUSH_IDLE_HOURS = 20  # silence before someone is worth a nudge
PUSH_COOLDOWN_HOURS = 48  # never nudge the same person more often
PUSH_BATCH = 40  # per tick, so a big base is spread over hours
PUSH_FREE_VIEWS = 1  # circles handed out with the reminder
PUSH_TICK = 900.0  # seconds between sweeps

# --- welcome and promo posts ---
PROMO_ENABLED = 1
PROMO_EVERY_CIRCLES = 20  # circles between one ad break and the next

# Everything a user sees a date or a daily reset in runs on Moscow time: the
# server may sit anywhere, and «сбросится в полночь» has to mean one thing.
# Moscow has not shifted its clocks since 2014, so a fixed offset is enough.
MSK_OFFSET = 3 * 3600

# --- paid subscriptions ---
# Priced per day in coins. A+ buys a daily allowance of free circles, the two
# above it buy the allowance away entirely and let circles be saved.
TIER_A1_PRICE = 80
TIER_A2_PRICE = 100
TIER_PRO_PRICE = 150
TIER_A1_VIEWS = 100  # free circles a day on A+
TIER_PRO_PENDING = 50  # unmoderated uploads Premium may hold at once

# --- paid reach for a profile ---
# Everyone is shown once per lap of the feed, so what is sold is being drawn
# early rather than being drawn again — see db.pick_profile. Sold by the day:
# a run renews, while a bundle of impressions is bought once and is also a
# debt the feed then owes.
BOOST_PACKS = ((1, 0), (7, 17), (30, 33))  # (дней, % скидки за срок)
BOOST_PRICE = 120  # coins a day at full price
BOOST_WEIGHT = 5  # how many times likelier a boosted card is to come up

# --- cheques ---
CHEQUE_MIN_REFS = 3  # invited friends a «refs» cheque asks for

REPORTS_TO_HIDE = 5  # complaints that pull a circle out of rotation on their own

# --- author profiles and payouts ---
AUTHOR_SHARE = 50  # percent of a sale that reaches the author
PRICE_MIN = 1
PRICE_MAX = 10_000
PAYOUT_MIN = 1000  # coins
PAYOUT_RATE = 3  # coins per star when cashing out
ABOUT_MAX = 300  # characters in a profile description

# --- ad accounting ---
CURRENCY = "₽"
STAR_PRICE = 130  # what one ⭐ is worth to you, in minor units (1.30 ₽)
# What Telegram sells stars for, near enough: 50 ⭐ ≈ $0.75. This is the price
# the crypto checkout is judged against — the panel shows both and complains
# when they drift apart, because the cheaper door is the one everybody uses.
STARS_PER_USD = 67
# Crypto has its own number so a discount stays possible, but it must stay in
# the same world as the stars: at STAR_COST=2 a coin is 2 ⭐ ≈ $0.03, so a
# dollar buys about 33. It used to say 200 — six coins for the price of one.
USDT_RATE = 33  # coins for 1 USDT
CRYPTO_ASSET = "USDT"  # what invoices are issued in, both providers
# Card price of one coin, in kopecks. Defaults to what a coin costs in stars
# (STAR_COST × STAR_PRICE), so the three checkouts start out at the same price.
CARD_PRICE = STAR_COST * STAR_PRICE
# Added on top of that price at checkout. The payer sees the total on the
# payment form before they pay anything.
CARD_FEE = 11  # percent

# --- legal ---
# Both documents have to be one tap from every screen where money changes
# hands: card acquirers check for exactly that. The wording also lives in
# docs/*.txt, so a page that gets lost can be republished from the repo.
TERMS_URL = "https://telegra.ph/PUBLICHNAYA-OFERTA-08-28-19"
PRIVACY_URL = "https://telegra.ph/POLITIKA-KONFIDENCIALNOSTI-08-28-90"

# Channel users must join before they can use the bot; empty turns the gate off.
# The bot has to be an administrator there to see who is a member.
CHANNEL: str = os.getenv("CHANNEL", "")
SUB_CACHE = 0.0  # seconds a confirmed subscription is trusted without asking

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is missing, fill .env")
if not ADMIN_CHAT_ID:
    raise RuntimeError("ADMIN_CHAT_ID is missing, fill .env")

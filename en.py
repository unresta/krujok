"""English versions of every text the user can see.

Same keys as the module-level names in texts.py: `_fmt` and `t()` look here
first when the update is being answered in English, and fall back to the
Russian one when a key is missing — a text that has not been translated yet
still comes out, in the wrong language rather than not at all.

The inserts must match the Russian template's: the code fills the same {names}
for both. The panel edits the Russian texts; the English ones ship with the
code, which is why they are here and not in the settings table.
"""

TEXTS: dict[str, str] = {}

# --- main menu, feed, rules ----------------------------------------------
TEXTS["MENU"] = (
    "<b>Circles</b>\n\n"
    "{coin} Balance: <b>{coins}</b>\n"
    "{film} Feed: <b>{pref}</b>\n\n"
    "Buttons are below."
)
TEXTS["FEED"] = (
    "<b>Feed</b>\n\n"
    "Showing right now: <b>{pref}</b>\n"
    "Pick which circles you want to watch."
)
TEXTS["RULES"] = (
    "\u2139\ufe0f <b>Service rules</b>\n\n"
    "\u2022 Not allowed: LGBT material, nude videos of anyone under 18, "
    "advertising, spam, abuse and anything illegal\n"
    "\u2022 A circle must be at least {min_duration} seconds long\n"
    "\u2022 Respect other people and do not abuse the report button\n\n"
    "Breaking the rules can cost you access to the bot without warning."
)
TEXTS["FAQ"] = (
    "\u2753 <b>FAQ</b>\n\n"
    "<b>Where do coins come from?</b>\n"
    "Buy them for \u2b50 in the Shop, or sell your own content: people buy "
    "access to your circles and {author_share}% of the price is yours. "
    "A friend who joins through your link is worth {ref_reward} more.\n\n"
    "<b>What does watching cost?</b>\n"
    "{watch_cost} coins per circle. The same circle never comes up twice, and "
    "your own are never shown to you.\n\n"
    "<b>How do I earn?</b>\n"
    "By selling only: someone buys access to all your circles or to your "
    "contact, and {author_share}% of the price goes to you. Uploading itself "
    "pays nothing.\n\n"
    "<b>Then why upload at all?</b>\n"
    "It is the only way anyone finds you: a viewer watches a circle and opens "
    "your profile from the button under it. The more likes a circle collects, "
    "the more people are shown it.\n\n"
    "<b>What is a profile?</b>\n"
    "Your shop window: photo, description and your prices. Fill it in under "
    "Profile \u2192 My profile, it goes through review, and then it is shown "
    "in Browse profiles.\n\n"
    "<b>How do I cash out?</b>\n"
    "Profile \u2192 Withdraw: from {payout_min} coins, at {payout_rate} coins "
    "per \u2b50. Only earned coins can be withdrawn \u2014 the ones you bought "
    "for \u2b50 cannot. An admin closes the request by hand.\n\n"
    "<b>Why was my circle turned down?</b>\n"
    "Either it is shorter than the minimum, or the same one is already in the "
    "base, or a moderator found it against the rules.\n\n"
    "<b>How long is the review?</b>\n"
    "Usually not long. While one circle waits you can upload the next \u2014 "
    "up to {max_pending} at a time.\n\n"
    "<b>Can circles be saved or forwarded?</b>\n"
    "Not by default: they are sent with forwarding and saving switched off. "
    "The A++ and Premium subscriptions turn that off \u2014 see Subscription.\n\n"
    "<b>Can I bring people to my profile myself?</b>\n"
    "Yes. Profile \u2192 \ud83d\udd17 Link to my profile: put it in your "
    "channel or anywhere else. Whoever follows it lands straight on your "
    "profile and can buy access. The same screen counts how many came.\n\n"
    "<b>How do I get more views on my profile?</b>\n"
    "The \ud83d\ude80 Promotion button in My profile: while it is paid for, "
    "your profile goes first in the queue and far more people see it. When the "
    "run ends the bot tells you how many did.\n\n"
    "<b>What do subscriptions give me?</b>\n"
    "Watching stops costing coins: A+ gives a free daily allowance, A++ and "
    "Premium have no limit at all and add forwarding and saving. Premium also "
    "raises how many circles you may have in review. They are paid for in coins "
    "per day \u2014 the Subscription button in the menu.\n\n"
    "<b>Why do I need a profile to upload?</b>\n"
    "Because a circle and its author belong together: every circle carries an "
    "Author profile button, and that is how a viewer buys access to all of "
    "yours. Without a profile that road ends.\n\n"
    "<b>Who sees who I am?</b>\n"
    "Your profile shows only the photo and description you chose yourself. "
    "Your name and @username are never shown; your @username reaches a buyer "
    "only if you switched contact selling on and they paid for it.\n\n"
    "<b>What do I do about a violation?</b>\n"
    "The Report button under the circle. Reports go straight to moderators."
)

# --- referrals ------------------------------------------------------------
TEXTS["REFERRALS"] = (
    "\ud83d\udc65 <b>Referrals</b>\n\n"
    "Invited: <b>{done}</b>{waiting}\n"
    "Every friend who joins the channel is worth "
    "<b>+{ref_reward}</b> {coin}\n\n"
    "Your link:\n<code>{link}</code>"
)
TEXTS["REFERRALS_WAITING"] = " \u00b7 waiting to subscribe: {waiting}"

# --- watching -------------------------------------------------------------
TEXTS["NOT_ENOUGH"] = (
    "{coin} Balance: <b>{coins}</b> \u2014 a circle costs {watch_cost}.\n\n{earn}"
)
TEXTS["NOT_ENOUGH_UPLOAD"] = "Upload a circle ({reward}) or buy coins for \u2b50."
TEXTS["NOT_ENOUGH_SELL"] = (
    "There are two ways to get coins: buy them for \u2b50 in the Shop, or sell "
    "your own content \u2014 set up a profile, and everyone who buys access "
    "brings you {author_share}% of what they paid."
)
TEXTS["PUSH_NEW"] = (
    "<b>New circles have landed. Time to watch!</b>\n\n"
    "Press the button \u2014 {free} {circles} on the house \ud83d\udc40"
)
TEXTS["PUSH_MISSED"] = (
    "<b>You have not been around for a while \u2014 there are new faces here.</b>\n\n"
    "Here are {free} {circles} on the house \ud83d\udc40"
)
TEXTS["PUSH_WAITING"] = (
    "<b>Somebody recorded a circle while you were away.</b>\n\n"
    "The first {free} {circles} are free, then as usual \ud83d\udc40"
)

TEXTS["PUSH_UNACCEPTED"] = (
    "<b>You never got started 🙈</b>\n\n"
    "Nothing to confirm: {free} {circles} are already on your account — "
    "press and watch."
)
TEXTS["FREE_VIEW_LEFT"] = (
    "🎁 This one is on the house. Free circles left: <b>{left}</b>."
)
TEXTS["FREE_VIEW_LAST"] = (
    "🎁 That was the last free circle — from here it is the usual "
    "{watch_cost} {coin} a view."
)
TEXTS["TRIAL_PUSH"] = (
    "🎁 <b>You still have {left} {circles} for free!</b>\n\n"
    "Nothing to pay — just press the button."
)
TEXTS["EMPTY"] = (
    "No fresh circles of this kind — you have watched them all.\n"
    "Come back later or switch the type."
)
TEXTS["ARCHIVE_NOTE"] = (
    "This circle comes from the bot's archive — it has no author and no profile."
)
TEXTS["EARNED_TOAST"] = "Someone watched your circle: +{amount}"
TEXTS["LIKE_BONUS_NOTE"] = "👍 Someone liked your circle: +{amount}"

# --- uploading ------------------------------------------------------------
TEXTS["UPLOAD_NEEDS_PROFILE"] = (
    "🎬 A profile comes first.\n\n"
    "Circles are shown together with their author's profile: a viewer can open "
    "it and buy access to everything you have. Without a profile there is "
    "nothing to sell."
)
TEXTS["UPLOAD_WAIT_REVIEW"] = (
    "🕒 Your profile is in review. Once it is approved you can upload circles."
)
TEXTS["UPLOAD_PROFILE_REJECTED"] = (
    "🔴 Your profile was turned down. Fill it in again: Profile → My profile, "
    "then upload."
)
TEXTS["UPLOAD_ASK"] = (
    "🎥 Send one {kind} circle in a single message.\n\n"
    "• at least {min_duration} seconds\n{payoff}"
)
TEXTS["UPLOAD_ASK_PAID"] = "• <b>+{reward}</b> {coin} once a moderator approves it"
TEXTS["UPLOAD_ASK_FREE"] = (
    "• circles are not paid for — they are the shop window of your profile\n"
    "• each one carries an Author profile button: that is how people find and "
    "buy from you\n"
    "• the more likes, the more people are shown it"
)
TEXTS["NOT_A_CIRCLE"] = (
    "That is not a circle. Hold 🎥 in the input field and record a video message."
)
TEXTS["TOO_SHORT"] = (
    "A {duration} sec circle is too short. The minimum is {min_duration} seconds."
)
TEXTS["DUPLICATE"] = "That circle is already in the base."
TEXTS["TOO_MANY_PENDING"] = (
    "You already have several circles in review. Wait for a decision."
)
TEXTS["UPLOAD_SENT"] = "✅ Circle <b>#{circle_id}</b> sent for review.\n{tail}"
TEXTS["UPLOAD_SENT_PAID"] = "Once approved: <b>+{reward}</b> {coin}"
TEXTS["UPLOAD_SENT_FREE"] = (
    "Once approved it will be shown together with your profile."
)
TEXTS["APPROVED_PAID"] = (
    "🟢 Your circle is approved: <b>+{reward}</b> {coin}\nBalance: <b>{coins}</b>"
)
TEXTS["APPROVED_FREE"] = (
    "🟢 Your circle is approved — people are being shown it.\n"
    "Collect likes: the more it has, the more often it comes up, and the more "
    "often your profile is opened."
)

# --- moderation verdicts an author reads ----------------------------------
TEXTS["REJECTED"] = "🔴 A moderator turned your circle down.{reason}"
TEXTS["CIRCLE_REASON_TAIL"] = "\n\nReason: <b>{reason}</b>"
TEXTS["CIRCLE_DELETED"] = "🔴 Your circle was deleted.{reason}"
TEXTS["REASON_REPORTS"] = "reports from users"
TEXTS["REASON_HIDDEN"] = "taken off display by a moderator"
TEXTS["CIRCLE_REMOVED"] = "🔴 Your circle was deleted after reports."
TEXTS["CIRCLE_HIDDEN"] = (
    "🚫 Your circle was taken off display — a moderator found it against the rules."
)
TEXTS["CIRCLE_RESTORED"] = "🟢 Your circle was reviewed and is back on display."

# --- complaints -----------------------------------------------------------
TEXTS["REPORT_SENT"] = "Your report went to the moderators."
TEXTS["REPORT_DOUBLE"] = "You have already reported this circle."
TEXTS["REPORT_DOUBLE_PROFILE"] = "You have already reported this profile."
TEXTS["REPORT_ASK"] = "What are you reporting it for?"
TEXTS["NO_REASON"] = "no reason given"

# --- buying coins ---------------------------------------------------------
TEXTS["BUY"] = (
    "{coin} Balance: <b>{coins}</b>\n\n"
    "1 {coin} = <b>{star_cost}</b> ⭐, {min_stars} ⭐ minimum."
)
TEXTS["BUY_CUSTOM"] = "How many ⭐ shall we charge? Send a number ({min_stars} or more)."
TEXTS["BUY_CHOOSE_METHOD"] = (
    "💰 <b>Buying {coins} coins</b>\n\n"
    "Total: <b>{stars} ⭐</b> → <b>{coins}</b> {coin}{bonus}\n\n"
    "Pick how to pay:"
)
TEXTS["BUY_CARD_BONUS"] = "\n💳 By card: <b>{total}</b> {coin} — {percent}% more"
TEXTS["BUY_PICK_METHOD"] = (
    "Pick how to pay with a button under the message above."
)
TEXTS["BUY_BAD_INPUT"] = "It has to be a whole number, {min_stars} or more."
TEXTS["CRYPTO_INVOICE"] = (
    "🧾 <b>Invoice for {amount} {asset}</b>\n\n"
    "You get: <b>{coins}</b> {coin}{bonus}\n"
    "Paid through {provider}.\n\n"
    "Press Pay, and once you have paid — Check. The coins arrive by themselves "
    "within a minute.\n"
    "The invoice is good for {minutes} minutes."
)
TEXTS["INVOICE_BONUS"] = "\n🎁 <b>+{bonus}</b> {coin} of that is the card bonus"
TEXTS["CRYPTO_PAID"] = (
    "🟢 Paid {amount} {asset} → <b>+{coins}</b> {coin}\nBalance: <b>{balance}</b>"
)
TEXTS["CRYPTO_PENDING"] = (
    "The payment has not arrived yet. If you have just sent it, give it a minute."
)
TEXTS["CRYPTO_EXPIRED"] = "This invoice has expired. Make a new one in the Shop."
TEXTS["CRYPTO_CANCELLED"] = "Invoice cancelled."
TEXTS["CRYPTO_FAILED"] = (
    "😕 Could not raise an invoice — the payment service did not answer.\n"
    "Try again or pick another way to pay."
)
TEXTS["CRYPTO_GONE"] = "Invoice not found."
TEXTS["PAID"] = (
    "🟢 Paid {stars} ⭐ → <b>+{added}</b> {coin}\nBalance: <b>{coins}</b>"
)

# --- the user's own profile screen ---------------------------------------
TEXTS["PROFILE"] = (
    "{icon_profile} <b>Your profile:</b>\n\n"
    "{icon_uploaded} Circles uploaded: <b>{approved}</b>\n"
    "{icon_ratings} Ratings: {icon_like} <b>{likes}</b> | {icon_dislike} <b>{dislikes}</b>\n"
    "{icon_views} Circles watched: <b>{watched}</b>\n"
    "{icon_balance} Balance: <b>{coins}</b> {icon_coin}{withdraw}\n\n"
    "{icon_earnings} <b>Want to earn on Krujok — press My profile 👇</b>\n\n"
    "👥 People invited: {ref_done}\n"
    "🛒 Sold: {sold_content} accesses · {sold_contact} contacts\n"
    "👀 Views on your circles: {views}"
)
TEXTS["PROFILE_WITHDRAW"] = (
    "\n💸 Of that you can withdraw: <b>{withdrawable}</b> (~{stars} ⭐)"
)
TEXTS["MY_CIRCLES"] = (
    "📤 <b>My uploaded circles:</b>\n\n"
    "🟢 Approved: {approved}\n"
    "🕒 In review: {pending}\n"
    "🔴 Turned down: {rejected}\n\n"
    "Total: {total}"
)
TEXTS["MY_CIRCLES_EMPTY"] = "You have not uploaded anything yet."
TEXTS["MY_CIRCLE_GONE"] = "That circle is gone."
TEXTS["MY_CIRCLE_ASK"] = (
    "Delete this circle? It goes for good — along with its views and likes, and "
    "for the people who bought access too. This cannot be undone."
)
TEXTS["MY_CIRCLE_DELETED"] = "Circle deleted."
TEXTS["MY_CIRCLES_STATUS_EMPTY"] = "Nothing here."
TEXTS["MY_CIRCLES_DONE"] = "That is all of them."
TEXTS["MY_CIRCLES_MORE"] = "{left} {circles} left."
TEXTS["MY_CIRCLE_INFO"] = (
    "Circle #{circle_id}\n"
    "Uploaded: {date}\n"
    "Length: {duration} sec\n"
    "Views: {views}\n"
    "Likes: {likes} · dislikes: {dislikes}\n"
    "Earned: {earned}"
)
TEXTS["MY_CIRCLE_INFO_REASON"] = "\n\nTurned down for: {reason}"
TEXTS["BOUGHT_EMPTY"] = "You have not bought anything yet."
TEXTS["BOUGHT_HEADER"] = "🛒 <b>Circles you have bought:</b>\n"

# --- author profile: filling it in ---------------------------------------
TEXTS["PROFILE_INTRO"] = (
    "<b>Want to earn on Krujok?</b>\n\n"
    "1. 👤 <b>Make your profile look good.</b>\n"
    "— Set a fair price\n"
    "— Put up a good photo\n"
    "— Write a description people want to read\n\n"
    "2. 🔞 <b>Upload interesting circles</b> to pull more people in\n\n"
    "3. ❓ <b>How does it work?</b>\n"
    "People are shown your circles and can open your profile from them. So make "
    "the profile worth opening and keep the circles coming\n\n"
    "4. 💸 <b>Ways to take the money out:</b>\n"
    "Crypto 💰\n"
    "Telegram Stars ⭐\n"
    "Card transfer 💳\n\n"
    "Press the button below to agree and start setting up your profile."
)
TEXTS["PROFILE_PHOTO"] = (
    "🖼 <b>My profile</b>\n\n"
    "Send a photo for it — everyone browsing profiles will see it.\n"
    "You do not have to show your face."
)
TEXTS["PROFILE_ABOUT"] = (
    "✍️ Now a description — a line or two about yourself.\n"
    "Up to {limit} characters. Send «-» to leave it empty."
)
TEXTS["PROFILE_ABOUT_TEXT_ONLY"] = (
    "The description has to be text. Send «-» to leave it empty."
)
TEXTS["PROFILE_GENDER"] = "Who are you?"
TEXTS["PROFILE_PRICE_CONTENT"] = (
    "💰 The price of access to <b>all your circles</b>, in coins.\n"
    "From {price_min} to {price_max}.\n\n"
    "You keep {author_share}% of every purchase."
)

TEXTS["PROFILE_CONTACT_ASK"] = (
    "Sell access to your contact? The buyer gets your @username and can write "
    "to you directly.\n\nThat is the end of your anonymity — your call."
)
TEXTS["PROFILE_NO_USERNAME"] = (
    "Selling your contact needs a @username.\n\n"
    "Telegram settings → Username. Once it is set, press «I added a username» "
    "and contact selling opens up.\n"
    "If you would rather not, we sell only the circles."
)
TEXTS["PROFILE_STILL_NO_USERNAME"] = (
    "I still cannot see a @username. Set it in Telegram settings and press again."
)
TEXTS["PROFILE_PRICE_CONTACT"] = (
    "💬 The price of access to your contact, in coins.\nFrom {price_min} to {price_max}."
)
TEXTS["PROFILE_BAD_PRICE"] = "It has to be a number from {price_min} to {price_max}."
TEXTS["PROFILE_SENT"] = (
    "✅ Your profile went for review. As soon as a moderator approves it, "
    "people will start seeing it."
)
TEXTS["PROFILE_NOT_PHOTO"] = "It has to be a photo."
TEXTS["PROFILE_APPROVED"] = "🟢 Your profile is approved — people are seeing it."
TEXTS["PROFILE_FIELD_SAVED"] = "✅ {field} updated.\n📬 The profile went back for review."
TEXTS["PROFILE_PRICE_SAVED"] = "✅ {field}: <b>{price}</b> {coin}.\nAlready in force."
TEXTS["PROFILE_CONTACT_OFF"] = (
    "✅ Your contact is no longer for sale. Already in force."
)
TEXTS["PROFILE_REVERTED"] = (
    "🔴 The changes to your profile were turned down.{reason}\n\n"
    "The previous version is back and on display. You can edit it again."
)
TEXTS["PROFILE_REJECTED"] = (
    "🔴 A moderator turned your profile down.{reason}\n\n"
    "Fill it in again — it takes a minute. Without a profile you cannot upload "
    "circles or earn from them."
)
TEXTS["PROFILE_REASON_TAIL"] = "\n\nReason: <b>{reason}</b>"
TEXTS["PROFILE_FROZEN"] = (
    "🚫 <b>Your profile was taken off display after reports.</b>{reason}\n\n"
    "It has not gone anywhere. Open My profile, fix what people complained "
    "about, and it goes back for review by itself. Your circles and coins stay "
    "with you."
)
TEXTS["PROFILE_FROZEN_REASONS"] = "\n\nWhat people reported:\n{list}"
TEXTS["PROFILE_EMPTY_WAIT"] = (
    "No profiles left — you have seen them all. Come back later."
)
TEXTS["PROFILE_EMPTY_PITCH"] = (
    "There are no profiles yet — but you could be the first.\n\n"
    "A profile is your shop window: photo, description and your price. Other "
    "people buy access to all your circles, and <b>{author_share}%</b> of every "
    "purchase is yours. Earnings are withdrawn in ⭐ from {payout_min} coins.\n\n"
    "Circles cannot be uploaded without a profile — everything starts here."
)
TEXTS["STATUS_PENDING"] = "🕒 in review"
TEXTS["STATUS_APPROVED"] = "🟢 on display"
TEXTS["STATUS_REJECTED"] = "🔴 turned down"
TEXTS["CONTACT_NOT_SOLD"] = "not for sale"
TEXTS["PROFILE_STATUS"] = (
    "<b>My profile</b> · {status}\n\n"
    "{about}\n\n"
    "Circles: {price_content} {coin}\n"
    "Contact: {contact}\n"
    "Shown: {views} · bought: {sold}{boost}"
)
TEXTS["PROFILE_STATUS_BOOST"] = "\n🚀 Promoted until {left}"

TEXTS["PROFILE_CARD"] = (
    "<b>{who}</b>\n\n"
    "{icon_about} {about}\n\n"
    "{icon_count} Circles by this author: <b>{circles}</b>\n"
    "{icon_price} Access to all of them: <b>{price_content}</b> {coin}\n"
    "Contact: {contact}\n"
    "{icon_sold} Bought: {sold} times\n\n"
    "{icon_info} <i>Buying opens the circles the author has right now.</i>"
)

# --- buying from an author ------------------------------------------------
TEXTS["BOUGHT_CONTENT"] = (
    "🟢 Access open: {count} {circles} by this author are free for you now.\n"
    "Press «Author's circles» to watch them."
)
TEXTS["BOUGHT_CONTACT"] = "🟢 The author's contact: @{username}\n\nWrite to them yourself."
TEXTS["SALE_NOTE"] = "💰 Someone bought {what}: <b>+{share}</b> {coin}"
TEXTS["SALE_KIND_CONTENT"] = "access to your circles"
TEXTS["SALE_KIND_CONTACT"] = "your contact"
TEXTS["MORE_CIRCLES"] = "{left} more {circles} by this author."
TEXTS["CONTACT_NOT_FOR_SALE"] = "This author does not sell their contact."
TEXTS["NOTHING_TO_SELL"] = "The author has no circles yet — nothing to buy."
TEXTS["ALREADY_BOUGHT"] = "Already bought."

# --- topping an old purchase up to today's catalogue ----------------------
TEXTS["TOPUP_OPEN"] = (
    "\n\n🎬 {have} of {total} open — you can add the other {missing} for {cost} {coin}"
)
TEXTS["TOPUP_SOON"] = (
    "\n\n🎬 {have} of {total} open. The author has posted new ones — you will be "
    "able to add them once there are {left} {circles} more"
)
TEXTS["TOPUP_ALL"] = "\n\n🎬 Everything the author has is open: {have}"
TEXTS["TOPUP_DONE"] = (
    "🟢 Added: {added} more {circles} are open.\n"
    "That makes {total} — press «Author's circles»."
)
TEXTS["TOPUP_NEWS"] = (
    "🎬 The author whose circles you bought has new ones: "
    "<b>{missing}</b> {circles}.\n"
    "Opening them costs <b>{cost}</b> {coin}."
)
TEXTS["TOPUP_GONE"] = "The author has no new circles yet."
TEXTS["TOPUP_SMALL"] = "Too few new ones so far — you can add them later."

# --- payouts -------------------------------------------------------------
TEXTS["PAYOUT_SCREEN"] = (
    "💸 <b>Withdraw</b>\n\n"
    "Available to withdraw: <b>{available}</b> {coin} (~{stars} ⭐)\n"
    "Rate: {rate} coins = 1 ⭐, {low} coins minimum\n\n"
    "Only earned coins can be withdrawn — the ones bought for ⭐ cannot. Inside "
    "the bot the bought ones are spent first, so your earnings stay "
    "whole.{spent}{pending}"
)
TEXTS["PAYOUT_SCREEN_SPENT"] = (
    "\n\n{coin} Another {spent} of your earnings went on things inside the bot."
)
TEXTS["PAYOUT_SCREEN_PENDING"] = "\n\n🕒 Requests in progress: {pending}"
TEXTS["PAYOUT_ASK_AMOUNT"] = (
    "How many coins do you want to withdraw? {available} available, {low} minimum."
)
TEXTS["PAYOUT_NOT_A_NUMBER"] = "It has to be a number — digits only, no spaces or letters."
TEXTS["PAYOUT_OVER_AVAILABLE"] = (
    "You do not have that much: <b>{available}</b> coins are available."
)
TEXTS["PAYOUT_UNDER_MIN"] = "That is below the minimum — we pay out from <b>{low}</b> coins."

TEXTS["PAYOUT_ASK_DETAILS"] = (
    "Where should it go? Send a wallet address (USDT/TON) or your @username — "
    "an admin will get in touch and pay out."
)
TEXTS["PAYOUT_CREATED"] = (
    "✅ Request <b>#{payout_id}</b> created: {coins} {coin} → {stars} ⭐.\n"
    "The coins are on hold. An admin pays out by hand and closes the request."
)
TEXTS["PAYOUT_PAID"] = "🟢 Request #{payout_id} paid: {stars} ⭐."
TEXTS["PAYOUT_REJECTED"] = (
    "🔴 Request #{payout_id} was turned down, {coins} coins are back on your balance."
)
TEXTS["PAYOUT_SPENT"] = (
    "There are only {balance} coins on the balance and the request needs "
    "{wanted}: the earnings have already gone on views or purchases."
)
TEXTS["PAYOUT_TOO_SMALL"] = (
    "The minimum payout is {low} coins. You have {available} available."
)

# --- cheques --------------------------------------------------------------
TEXTS["CHEQUE_POST"] = (
    "🎟 <b>A cheque for {coins} coins</b>\n\n"
    "Uses left: <b>{total}</b>\n"
    "Press the button — the coins land on your balance."
)
TEXTS["CHEQUE_CLAIMED"] = (
    "🎟 Cheque claimed: <b>+{coins}</b> {coin}\nBalance: <b>{balance}</b>"
)
TEXTS["CHEQUE_NEEDS_REFS"] = (
    "🎟 This cheque is for people who bring friends.\n\n"
    "Invited needed: <b>{need}</b>, you have: <b>{have}</b>.\n"
    "Invite friends with your link and come back — the cheque waits until its "
    "uses run out."
)
TEXTS["CHEQUE_GONE"] = "🎟 No such cheque — it may have been deleted."
TEXTS["CHEQUE_TAKEN"] = "🎟 You have already claimed this cheque."
TEXTS["CHEQUE_EMPTY"] = "🎟 All uses are gone — this cheque has been taken apart."

# --- gate, subscription ---------------------------------------------------
TEXTS["ACCEPTED"] = "Done. Enjoy 🙂"
TEXTS["SUBSCRIBE"] = (
    "📢 The bot works for subscribers only.\n\n"
    "Do what the buttons below say — join {what} — and press "
    "«I subscribed».{gift}"
)
TEXTS["SUBSCRIBE_ONE"] = "the channel"
TEXTS["SUBSCRIBE_MANY"] = "all the channels"
TEXTS["SUBSCRIBE_SPONSORS"] = "all the sponsors"
TEXTS["SUBSCRIBE_GIFT"] = "\n\n🎁 Subscribing is worth <b>{bonus}</b> coins."
TEXTS["SUB_BONUS"] = "🎁 Thanks for subscribing: <b>+{amount}</b> {coin}"
TEXTS["SUBSCRIBE_MISSING"] = (
    "I cannot see your subscription. Join the channel and press again."
)
TEXTS["SUBSCRIBE_OK"] = "Done 🟢"
TEXTS["REFERRAL_PAID"] = (
    "🟢 A friend came through your link: <b>+{reward}</b> coins.\n"
    "Invited in total: {done}"
)
TEXTS["BANNED"] = "Access closed."
TEXTS["MAINTENANCE"] = "🔧 The bot is under maintenance. Look in a little later."

# --- short answers to a tap ----------------------------------------------
TEXTS["VOTE_CANCEL"] = "Taken back"
TEXTS["PROFILE_NOTHING_TO_HIDE"] = "Nothing to hide."
TEXTS["PROFILE_HIDDEN_TOAST"] = "Profile hidden."
TEXTS["PROFILE_SAVED_TOAST"] = "Done 🟢"
TEXTS["CONTACT_OFF_TOAST"] = "Your contact is no longer for sale."
TEXTS["USERNAME_SEEN"] = "I see it 🟢"
TEXTS["BUY_NO_AMOUNT"] = "No amount picked — start again."
TEXTS["BUY_CARD_SOON"] = "⚠️ That way of paying is unavailable right now. Pick another."
TEXTS["SENDING_CIRCLES"] = "Sending {count}"
TEXTS["CIRCLES_LOST"] = (
    "⚠️ {sent} of {total} arrived.\n\n"
    "Telegram would not let the rest through — press the button again in a minute."
)

TEXTS["AUTHOR_NO_PROFILE"] = "Author without a profile"
TEXTS["BOUGHT_ROW"] = "{index}. {who} — {count} {circles}"

# --- what the code says when something is off ----------------------------
TEXTS["CIRCLE_GONE"] = "That circle is already gone."
TEXTS["CIRCLE_NOT_SHOWN"] = "This circle was never shown to you."
TEXTS["CIRCLE_OWN_VOTE"] = "Rating your own circle would not be fair 🙂"
TEXTS["PROFILE_GONE"] = "That profile is gone."
TEXTS["PROFILE_OWN"] = "That is your own profile 🙂"
TEXTS["PROFILE_NONE_YET"] = "This author has no profile."
TEXTS["NEED_PROFILE_FIRST"] = "Fill in your profile first."
TEXTS["NOT_SO_FAST"] = "Not so fast 🙂"
TEXTS["SEND_FAILED"] = "Could not send the circle, the coins are back."
TEXTS["BUY_FIRST"] = "Buy access first."
TEXTS["AUTHOR_EMPTY"] = "This author has nothing to watch yet."
TEXTS["NOT_ENOUGH_COINS_TOAST"] = "Not enough coins."
TEXTS["BOUGHT_TOAST"] = "Bought 🟢"
TEXTS["STALE_BUTTON"] = "That button is out of date"

# --- paid subscriptions ---------------------------------------------------
TEXTS["TIERS_HEADER"] = "⭐ <b>Pick a subscription:</b>"
TEXTS["TIERS_ACTIVE"] = "🟢 You have <b>{tier}</b> right now — until {until} ({left})."
TEXTS["TIERS_BALANCE"] = "{coin} Balance: <b>{coins}</b>"
TEXTS["TIER_CARD"] = (
    "<b>{tier}</b> · {price} {coin}/day\n\n"
    "{perks}\n\n"
    "{coin} Balance: <b>{coins}</b>\n"
    "Pick how long you are taking it for:"
)
TEXTS["TIER_SWITCH"] = (
    "⚠️ <b>{current}</b> is running right now, with {left} to go.\n"
    "Another subscription takes its place — the days left are lost."
)
TEXTS["TIER_BOUGHT"] = (
    "🟢 <b>{tier}</b> for {days} — {price} {coin} charged.\n"
    "Works until <b>{until}</b>."
)
TEXTS["TIER_PAY"] = (
    "<b>{tier}</b> for {days}\n\n"
    "{coin} In coins: <b>{price}</b> — once, renewed by hand.\n"
    "{recurring}"
)
TEXTS["TIER_PAY_RECURRING"] = (
    "🔁 Auto-renewing: <b>{rubles} ₽</b> {every} over SBP — access will not run "
    "out on its own, and you can switch it off at any time."
)
TEXTS["TIER_PAY_COINS_ONLY"] = "Paid in coins from your balance."
TEXTS["TIER_SUB_INVOICE"] = (
    "🧾 <b>Invoice for {amount} ₽</b>\n\n"
    "<b>{tier}</b>, charged {every}.\n"
    "Paid over SBP. After the first payment access switches on by itself and "
    "keeps renewing without you.\n\n"
    "You can switch it off at any time under Subscription.\n"
    "The invoice is good for {minutes} minutes."
)
TEXTS["TIER_SUB_CHARGED"] = (
    "🟢 <b>{tier}</b> paid: {amount} ₽.\nWorks until <b>{until}</b>."
)
TEXTS["TIER_SUB_RENEWED"] = (
    "🔁 <b>{tier}</b> renewed: {amount} ₽ charged.\nUntil <b>{until}</b>."
)

TEXTS["TIER_SUB_OVER"] = (
    "🔁 Auto-renewal is off — there will be no more charges. The time you have "
    "already paid for runs to the end."
)
TEXTS["TIER_SUB_FAILED"] = (
    "🔁 Auto-renewal stopped: a charge did not go through. The paid time runs to "
    "the end, and you can start it again under Subscription."
)
TEXTS["TIER_SUB_ACTIVE"] = (
    "🔁 <b>Auto-renewal is on</b>\n\n"
    "{tier} · {amount} ₽ {every}\n"
    "Next charge: <b>{next}</b>"
)
TEXTS["TIER_SUB_WAITING"] = "🕒 The invoice is out but not paid yet."
TEXTS["TIER_SUB_NONE"] = "No auto-renewal."
TEXTS["TIER_SUB_DROPPED"] = "Auto-renewal switched off."
TEXTS["TIER_SUB_ALREADY"] = "You already have auto-renewal — switch that one off first."
TEXTS["TIER_POOR"] = "Not enough coins: {price} needed, {coins} on the balance."
TEXTS["TIER_LIMIT_HIT"] = (
    "Your {views} free {circles} for today are used up — from here it is the "
    "usual {watch_cost} {coin} a view. The limit resets at midnight Moscow time, "
    "and A++ and Premium have no limit at all."
)
TEXTS["TIER_VIEWS_LEFT"] = "🎁 On your subscription. Free ones left today: <b>{left}</b>."

# --- paid reach for a profile --------------------------------------------
TEXTS["BOOST_SCREEN"] = (
    "🚀 <b>Profile promotion</b>\n\n"
    "While it is paid for, your profile goes first in the queue — far more "
    "people see it.\n\n"
    "{coin} Balance: <b>{coins}</b>\n"
    "{state}\n\n"
    "Pick how long:"
)
TEXTS["BOOST_RUNNING"] = "🟢 Running — until {until} ({left})."
TEXTS["BOOST_IDLE"] = "⚪ Your profile is in the ordinary queue right now."
TEXTS["BOOST_BOUGHT"] = (
    "🟢 Promotion for {days} — {price} {coin} charged.\n"
    "Runs until <b>{until}</b>, your profile is already going first.\n"
    "When it ends I will tell you how many people saw it."
)
TEXTS["BOOST_POOR"] = "Not enough coins: {price} needed, {coins} on the balance."
TEXTS["BOOST_NEEDS_APPROVED"] = (
    "Nothing to promote yet: the profile has to be approved and visible in the "
    "feed. Come back once it is."
)
TEXTS["BOOST_REPORT"] = (
    "🚀 <b>The promotion has ended</b>\n\n"
    "Your profile was shown <b>{shown}</b> {shown_word} and access was bought "
    "<b>{sold}</b> {sold_word}.\n\n"
    "It is back in the ordinary queue — you can renew under My profile."
)

# --- a link to one's own profile -----------------------------------------
TEXTS["PROFILE_LINK_INTRO"] = "🔗 <b>You came in through an author's link.</b>"
TEXTS["PROFILE_LINK_SCREEN"] = (
    "🔗 <b>The link to your profile</b>\n\n"
    "<code>{link}</code>\n\n"
    "Put it in your channel, in your bio, anywhere. Whoever follows it lands "
    "straight on your profile and can buy access to your circles.\n\n"
    "Follows so far: <b>{hits}</b>"
)
TEXTS["PROFILE_LINK_NEEDS_APPROVED"] = (
    "You get the link once the profile is approved — there is nothing to show "
    "behind it yet."
)
TEXTS["PROFILE_LINK_GONE"] = "The profile that link led to is unavailable."
TEXTS["PROFILE_LINK_OWN"] = "That is a link to your own profile 🙂"

# --- auction --------------------------------------------------------------
TEXTS["AUCTION"] = (
    "🔨 <b>Auction: {prize}</b>\n\n"
    "Whoever puts in the most coins in {hours} takes the prize.\n"
    "{rule}\n\n"
    "⏳ Time left: <b>{left}</b>\n"
    "🏆 Leader: <b>{top}</b> {coin}\n"
    "💰 Your bid: <b>{mine}</b> {coin} · your balance: {coins}\n"
    "👥 Bidders: {bidders}\n\n"
    "Bids add up: press again and yours grows."
)
TEXTS["AUCTION_RULE_BACK"] = (
    "Coins are taken straight away. Everyone but the winner gets every one of "
    "them back when the auction ends."
)
TEXTS["AUCTION_RULE_KEEP"] = (
    "Coins are taken straight away and <b>are not returned</b> — not to the "
    "winner, not to anyone. A bid is a bid."
)
TEXTS["AUCTION_OFF"] = "The auction is over. Look in next time 🙂"
TEXTS["AUCTION_BID_SMALL"] = "A bid has to be more than nothing."
TEXTS["AUCTION_BID_OK"] = "🔨 Taken. Your bid: {mine} coins"
TEXTS["AUCTION_POOR"] = "Not enough coins: {amount} needed, {coins} on the balance."
TEXTS["AUCTION_BID_ASK"] = (
    "🔨 How many coins do you want to bid?\n\n"
    "Send a number. It is added to your bid.\n"
    "Balance: <b>{coins}</b> {coin}"
)
TEXTS["AUCTION_WON"] = (
    "🏆 <b>You won the auction!</b>\n\n"
    "Your bid — <b>{coins}</b> {coin} — was the biggest one.\n\n"
    "Write to support{contact} for the prize — that is where it is handed over."
)
TEXTS["AUCTION_REFUND"] = (
    "🔨 The auction is over, the prize went to someone else.\n"
    "Your <b>{coins}</b> {coin} are back on your balance — every one of them."
)
TEXTS["AUCTION_LOST"] = (
    "🔨 The auction is over, the prize went to someone else.\n"
    "Your <b>{coins}</b> {coin} stay in the pot — as the auction screen said."
)
TEXTS["AUCTION_CANCELLED"] = (
    "🔨 The auction was called off. Your <b>{coins}</b> {coin} are back on your "
    "balance."
)
TEXTS["AUCTION_ANNOUNCE"] = (
    "🔨 <b>AUCTION: {prize}</b>\n\n"
    "You have {hours} to put in more coins than anyone else — one person takes "
    "the prize.\n{rule}\n\n"
    "The red «🔨 AUCTION» button is at the bottom, under the keyboard."
)
TEXTS["AUCTION_OUTBID"] = (
    "🔨 <b>You have been outbid!</b>\n\n"
    "The lead is now <b>{top}</b> {coin}, your bid is <b>{mine}</b>.\n"
    "Time left: <b>{left}</b>."
)

TEXTS["TRAFFER_UNKNOWN"] = (
    "That command does not fit — check it with whoever gave you the link."
)
TEXTS["TRAFFER_REPORT"] = (
    "📊 <b>{title}</b>\n\n"
    "🕓 <b>All time</b>\n"
    "New users: <b>{users}</b>\n"
    "Passed the subscription: {subscribed} ({subscribed_pct})\n"
    "Reached the bot: {accepted} ({accepted_pct})\n"
    "Bought coins: {payers} ({payers_pct})\n\n"
    "📅 7 days · people {week_users}, subscriptions {week_subscribed}\n"
    "📅 24 hours · people {day_users}, subscriptions {day_subscribed}\n\n"
    "<code>{link}</code>"
)

# --- lists whose keys are shared with the Russian ones --------------------
# Only the labels differ; the keys travel in callback data and in the database,
# so they are the same in both languages.

REPORT_REASONS = {
    "minor": "🧒 A minor in the video",
    "violence": "🩸 Violence or cruelty",
    "ads": "📢 Advertising or spam",
    "stolen": "🎭 Somebody else's circle",
    "other": "⚠️ Another violation",
}

PROFILE_REPORT_REASONS = {
    "photo": "🖼 The photo is stolen or off-topic",
    "minor": "🧒 A minor in the photo",
    "ads": "📢 Advertising or links in the profile",
    "scam": "💸 A scam, money outside the bot",
    "abuse": "🤬 Abuse in the description",
    "other": "⚠️ Another violation",
}

# What a moderator turns a circle down for, as the author reads it.
CIRCLE_REJECT_REASONS = {
    "minor": "a child in the circle",
    "quality": "poor quality: dark, blurred or nothing to see",
    "short": "an empty circle: nothing happens in it",
    "face": "no face, or not what was asked for",
    "ads": "advertising, links or contacts in the frame",
    "stolen": "somebody else's circle, not yours",
    "rules": "against the service rules",
    "unfit": "not suitable",
}

# The same for a profile.
REJECT_REASONS = {
    "photo": "the photo does not fit: stolen, off-topic or with no person in it",
    "about": "the description is off-topic or a string of symbols",
    "ads": "advertising, links or contacts in the profile",
    "rules": "against the service rules",
    "quality": "the photo quality is too poor",
}

MY_CIRCLES_STATUS = {
    "approved": "🟢 <b>Approved circles</b> — people are being shown them.",
    "pending": "🕒 <b>Circles in review</b> — a moderator has not decided yet.",
    "rejected": "🔴 <b>Turned down circles</b> — they are not shown.",
}

# Words that inflect in Russian and simply do not in English.
WORDS = {
    "circle": ("circle", "circles"),
    "day": ("day", "days"),
    "time": ("time", "times"),
    "hour": ("hour", "hours"),
    "no_description": "No description",
    "female": "female",
    "male": "male",
    "left": "left",
    "less_than_hour": "less than an hour",
    "less_than_minute": "less than a minute",
    "for_female": "for female",
    "for_male": "for male",
}

# --- language -------------------------------------------------------------
TEXTS["LANG_ASK"] = (
    "🌐 <b>Language</b>\n\n"
    "The bot speaks Russian and English. Pick whichever suits you — you can "
    "change it any time under Profile."
)
TEXTS["LANG_SET"] = "🌐 Done. English it is."

TEXTS["INVOICE_TITLE"] = "{coins} coins"
TEXTS["INVOICE_NOTE"] = "{stars} ⭐ → {coins} 🪙 on your balance in the bot."

TEXTS["CIRCLE_BLOCKED"] = (
    "🔇 <b>Telegram will not let circles through to you</b>\n\n"
    "Voice messages are switched off in your privacy settings, and a circle is "
    "a voice message as far as Telegram is concerned. Your coins are back.\n\n"
    "How to open it:\n"
    "1. Settings → <b>Privacy and Security</b>\n"
    "2. <b>Voice Messages</b>\n"
    "3. Set it to <b>Everybody</b> — or leave it and add this bot to the "
    "<b>Always Allow</b> exceptions\n\n"
    "Then press «Watch circles» again."
)

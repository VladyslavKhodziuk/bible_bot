# PLAN.md — Deploy fixes (Bible Way)

Checklist of pre-deploy fixes. Status: ✅ done · 📝 draft awaiting review · ⚙️ needs env var at deploy.

> i18n rule: every key change is applied to **all 4** locales `locales/{ru,en,es,uk}.yaml`.

---

## 1. ✅ Remove Russia flag in language settings
`keyboards/settings.py` — `changelang:ru` button now uses 🌍 (was 🇷🇺), matching the onboarding picker.

## 2. ✅ Clean up message after changing language
`handlers/settings.py` `apply_new_language` — replaced the confusing "👇 Кнопки внизу…" (`reply.intro`) message with a short `language.changed` confirmation ("✅ Язык изменён…"). That message still carries `main_reply_keyboard(new_lang)`, so the bottom reply keyboard refreshes to the new language (Telegram can't edit a reply keyboard in place). Popup alert dropped in favor of the message.

## 3. ✅ Rename "Wisdom of the day" → "Wisdom"
`menu.wisdom` and `wisdom.title` in all 4 locales:
ru `Мудрости`, uk `Мудрості`, en `Wisdom`, es `Sabiduría`.
(Remaining references inside onboarding/help/FAQ copy are folded into items 6–8.)

## 4. ✅ "Report a problem" button after AI Pastor reply
`handlers/ai_pastor.py` `_after_answer_keyboard` — added a 🐞 button (`feedback.cabinet_bug` → `fb:start:bug`, reusing the existing bug-report flow).

## 5. ✅ Clean editorial markup in default English Bible
`scripts/clean_bible_brackets.py` strips KJV brace notes `{x: y}`, brace inserted-words `{word}`, square-bracket additions/superscriptions `[…]`, and guillemet epistle subscriptions `«…»`; also cleans WEB/ASV `[…]`.
Result: `en_kjv` 17.4k verses, `en_asv` 3.9k, `en_web` 0.9k cleaned; 0 residual markup. Originals backed up to `data/bibles/*.bak` (do **not** commit the `.bak`).

## 6. 📝 Notification wording refresh
Keys: `greetings.{morning,day,evening,night}` (verse + plan push), `pray.notif.push_greeting`, `plan.push_title/push_today/push_reading`. Drafts pending review, then rolled out to 4 locales.

## 7. 📝 Onboarding text rewrite
`welcome.text` (+ related `welcome.*`, `onboarding.choose_timezone`). Drafts pending review.

## 8. 📝 /help text rewrite
`help.text`. Drafts pending review.

## 9. ✅ Plan duplication in "My account → My plans"
`handlers/plan.py` `show_history` — dedupe by `plan_id` (status priority active > completed > abandoned) so a restarted/abandoned plan renders once.

## 10. ⚙️ Bizum donation for Spain
- `config.py` — new `DONATE_BIZUM_PHONE` env var (button only renders when set).
- `keyboards/donate.py` — `donate.bizum_button` (region `spain`) + `donate_bizum_keyboard`; PayPal now also shows for `spain`.
- `handlers/donate.py` — shared `resolve_donate_region(user, lang)` routes es-UI **or** Spanish-timezone users (`Europe/Madrid`, `Atlantic/Canary`) to region `spain`; new `donate:bizum` info screen.
- `handlers/reply_menu.py` — the bottom «Поддержать» reply button (`reply_support`) now uses the same `resolve_donate_region` (was hardcoded `region="other"`, which hid Bizum on that path).
- i18n: `donate.bizum_button`, `donate.bizum_info` ({phone}) in all 4 locales.
- **Deploy:** set `DONATE_BIZUM_PHONE` in `.env`.

## 11. ✅ Random-verse message styling
`handlers/verse.py` `_format_verse` — verse wrapped in `<blockquote>`, reference on its own line with 📖 (also improves the verse-of-day card).

---

## Deploy steps
1. Set `DONATE_BIZUM_PHONE` in `.env` (item 10).
2. Confirm copy for items 6–8.
3. Restart the bot — cleaned Bibles and new i18n load at startup. `drop_pending_updates=True` clears the backlog.

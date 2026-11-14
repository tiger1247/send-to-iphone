# PhoneDrop – Microsoft Store listing

Paste these into Partner Center → your app → **Store listings → English (United States)**.

## Product name
PhoneDrop

## Short description (up to 270 characters, shown at the top of the listing)
Send photos, videos and files between your Windows PC and iPhone over Wi-Fi. No app, cable or account is needed on the iPhone: scan a QR code once and Safari becomes your transfer page.

## Description
PhoneDrop is the fastest way to move files between your Windows PC and your iPhone, with nothing to install on the phone.

Scan the QR code once with your iPhone camera. From then on:

• PC → iPhone: drag files onto PhoneDrop, or right-click any file → Share → PhoneDrop (it works from the Photos app too). Tap Save on your iPhone and the file goes to the Files app. Photos and videos can go straight to Photos.
• iPhone → PC: pick photos, videos or documents on your iPhone and they appear on your PC in Downloads\From iPhone.
• Shared clipboard: send a link or some text from one device and paste it on the other.
• Big files are fine: full-quality videos, with progress bars.
• Folders are sent as a single .zip.

Private by design
Files go directly over your own Wi-Fi network. They never pass through the internet or anyone's server. There are no accounts, ads or tracking. Only the iPhone that scanned your QR code can connect, and you can revoke it any time.

Lives quietly in your tray
PhoneDrop starts with Windows and waits in the system tray, ready whenever you need it.

Try it free for 7 days.

Requirements: your PC and iPhone must be on the same Wi-Fi network. Works with any iPhone or iPad with Safari.

iPhone and iPad are trademarks of Apple Inc. PhoneDrop is not affiliated with Apple.

## What's new in this version
First release.

## Product features (one per line, up to 20)
Send files from PC to iPhone without installing an app
Send photos and videos from iPhone to PC
Right-click any file → Share → PhoneDrop
Drag and drop files and folders
Shared clipboard between PC and iPhone
Works over your local Wi-Fi: no cloud, no account
Full-quality photos and videos, no size limit
QR code pairing: only your iPhone can connect
Starts with Windows and runs in the tray

## Search terms (up to 7)
iPhone file transfer
send files to iPhone
PC to iPhone
transfer photos iPhone
wifi file transfer
phone file transfer
iPhone to PC

## Category
Productivity (subcategory: none) — alternative: Utilities & tools

## Privacy policy URL
https://github.com/tiger1247/send-to-iphone/blob/main/PRIVACY.md

## Website / support
https://github.com/tiger1247/send-to-iphone
Support: https://github.com/tiger1247/send-to-iphone/issues

## Pricing and availability (Partner Center → Pricing and availability)
- Base price: **$2.99** (Microsoft converts it for other markets)
- Free trial: **7 days**
- Markets: all

## Age ratings
Complete the IARC questionnaire: no violence, no user-generated content shared publicly, no purchases inside the app, no location sharing → expect **3+ / Everyone**.

## Submission notes for certification (Partner Center → Submission options → Notes for certification)
PhoneDrop is a full-trust desktop app (runFullTrust) that runs a small local HTTP server on port 8765 so the user's iPhone can connect over the local network (privateNetworkClientServer + a private-profile firewall rule). To test: launch PhoneDrop, scan the QR code with any phone on the same Wi-Fi (or open the shown link in another device's browser), then send a file either way. No login is required.

## Screenshots
Upload in this order (Partner Center → Store listings → Screenshots → Desktop):
1. `packaging/store-assets/1-send-to-iphone.png`
2. `packaging/store-assets/2-iphone-to-pc.png`
3. `packaging/store-assets/3-private.png`

All are 1920×1080 (the Store needs at least 1366×768). Rebuild them with `build\venv\Scripts\python packaging\make_store_images.py`.

## Store logo (optional, Store listings → Store logos → 1:1 box art)
`packaging/store-assets/logo-300.png`

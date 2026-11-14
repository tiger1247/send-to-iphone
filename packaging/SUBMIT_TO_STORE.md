# Submitting PhoneDrop to the Microsoft Store

There are four parts. **You** do parts 1, 2 and 4 because they need your identity and account. **Claude** does part 3.

---

## 1. Create your developer account (free, about 10 minutes, then wait for verification)

1. Go to **https://storedeveloper.microsoft.com** and click **Get started** / **Sign up**.
2. Sign in with your personal Microsoft account.
3. Choose **Individual developer**.
4. Fill in your name, country and contact details, then complete identity verification (usually a photo ID and a selfie).
5. Approval can take from a few minutes to a few days. You'll get an email when it's done.

## 2. Reserve the name and copy your app's identity (2 minutes)

1. In **Partner Center** (https://partner.microsoft.com/dashboard/apps-and-games/overview) click **+ New product → MSIX or PWA app**.
2. Type **PhoneDrop** and click **Check availability → Reserve product name**.
   - If it's taken, try **PhoneDrop – File Transfer** or **PhoneDrop for PC**. Tell Claude which one you got.
3. Open **Product management → Product identity** and copy these 4 values:

| Partner Center shows | Example |
|---|---|
| Package/Identity/Name | `12345RishavSingh.PhoneDrop` |
| Package/Identity/Publisher | `CN=1A2B3C4D-....` |
| Package/Properties/PublisherDisplayName | `Rishav Singh` |
| Store ID | `9NXXXXXXXXXX` |

**Give these 4 values to Claude.** None of them are secret.

## 3. Claude builds the Store package

Claude puts the values into `packaging/store.json` and `src/storeapi.py`, then runs:

```
build\venv\Scripts\python packaging\build_msix.py --store packaging\store.json
```

The result is `build\PhoneDrop.msix`, stamped with your identity. The Store signs it, so no certificate is needed.

## 4. Fill in the submission and send it

In Partner Center → PhoneDrop → **Start your submission**:

| Section | What to do |
|---|---|
| **Pricing and availability** | Markets: all. Price: **$2.99**. Free trial: **7 days**. Visibility: Public. |
| **Properties** | Category **Productivity**. Privacy policy URL: `https://github.com/tiger1247/send-to-iphone/blob/main/PRIVACY.md`. Website: the GitHub repo. Leave system requirements at their defaults. |
| **Age ratings** | Answer the questionnaire: no violence, no chat, no user-generated content, no purchases inside the app, no location. Expect **3+**. |
| **Packages** | Drag in `build\PhoneDrop.msix`. Device family: **Desktop** only. |
| **Store listings → English** | Copy each field from `packaging/STORE_LISTING.md`. Screenshots: the 3 PNGs in `packaging/store-assets/`, in order. |
| **Submission options → Notes for certification** | Paste the note from `STORE_LISTING.md`. The `runFullTrust` capability needs a reason, and that note is it. |

Click **Submit to the Store**. Certification usually takes **1–3 business days**. Microsoft emails you if anything needs fixing. Send Claude their message and Claude will fix it and rebuild.

## After it's live

- Install PhoneDrop from the Store yourself to check the trial banner and the Buy button.
- **Updates:** bump `version` in `packaging/store.json` (for example `1.0.1.0`), rebuild, and upload the new `.msix` in a new submission.
- Sales reports and payouts are in Partner Center → **Payouts**. Set up your payout and tax profile there first, or you can't be paid.

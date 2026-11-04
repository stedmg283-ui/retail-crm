# WhatsApp Business API webhook setup

Run these steps on the PC that hosts the CRM.

## 1. Start the CRM

Open PowerShell, `cd` into the retail-crm folder, and run:

```powershell
flask --app wsgi run --port 5000
```

Leave this window open.

## 2. Start the tunnel

Open a second PowerShell window and run:

```powershell
cloudflared tunnel --url http://localhost:5000
```

Copy the fresh public link it prints (`https://something.trycloudflare.com`).

> **Note:** the link changes every time the tunnel restarts, so repeat step 3 with the new link each time.

## 3. Configure the webhook in Meta

1. Go to [Meta for Developers](https://developers.facebook.com), open your app, then **WhatsApp > Configuration**.
2. Set **Callback URL** to the fresh tunnel link plus `/webhook/whatsapp`, for example `https://something.trycloudflare.com/webhook/whatsapp`.
   (This is the CRM's actual route. `/webhooks/whatsapp` also works. `/whatsapp/webhook` returns 404.)
3. Set **Verify Token** to a word and number you choose and remember. Put the same value in the CRM's `.env` as `WHATSAPP_WEBHOOK_VERIFY_TOKEN` (see step 4) *before* clicking Verify, then restart the CRM.
4. Click **Verify and Save**.
5. Under Webhook fields, subscribe to **`messages`**.

## 4. Add the WhatsApp credentials to the CRM

From Meta's **WhatsApp > API Setup** page, copy the access token and the phone number ID into the CRM's `.env` file (in the retail-crm folder):

```
WHATSAPP_TOKEN=<access token>
WHATSAPP_PHONE_NUMBER_ID=<phone number ID>
WHATSAPP_WEBHOOK_VERIFY_TOKEN=<your verify token>
```

Restart the CRM after editing `.env`. Never commit `.env` to git.

## 5. Test

Re-run the invoice send test from the CRM (open a finalized invoice under **Sales** and click Send) to a customer's phone number.

## 6. Notes

- The temporary access token from API Setup **expires in 24 hours**. Generate a permanent token later, using a System User in Meta Business Settings.
- The Meta app must be **published** (Live mode) for production data to be delivered. While it's unpublished, only test webhooks sent from the app dashboard will arrive.

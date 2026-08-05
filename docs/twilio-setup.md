# Twilio setup for Texecom Alerts

This walks through the whole Twilio side: outbound texts, outbound voice calls,
and the inbound webhook that lets a keyholder acknowledge from the phone. It
assumes Home Assistant reaches Twilio for the outbound part, and that Twilio
reaches a relay for the inbound part.

The escalation ladder uses these in order: push first, then an SMS, then
repeating voice calls. So SMS and voice are what carry a real emergency to a
phone that is not looking at Home Assistant.

## 1. The Twilio account

1. Create an account at twilio.com and buy a phone number with both **Voice**
   and **SMS** capabilities. Note it in E.164 form, for example `+441632960000`.
2. From the Console dashboard note the **Account SID** and **Auth Token**.
3. On a trial account Twilio only calls and texts **verified** numbers, so add
   each keyholder number under Verified Caller IDs, or upgrade the account.

## 2. Outbound texts and calls

Home Assistant sends the SMS and the voice call through its Twilio notify
services. Those are configured in YAML, since the Twilio notify platforms have
no UI. Add the credentials to `secrets.yaml`:

```yaml
twilio_account_sid: ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
twilio_auth_token: your_auth_token
```

Then in `configuration.yaml`:

```yaml
twilio:
  account_sid: !secret twilio_account_sid
  auth_token: !secret twilio_auth_token

notify:
  - name: texecom_sms
    platform: twilio_sms
    from_number: "+441632960000"
  - name: texecom_call
    platform: twilio_call
    from_number: "+441632960000"
```

Restart Home Assistant. You now have `notify.texecom_sms` and
`notify.texecom_call`.

## 3. Point the integration at them

In the Texecom Alerts options:

- **SMS notify service**: `notify.texecom_sms`
- **Voice call notify service**: `notify.texecom_call`
- **Recipients**: every keyholder number in E.164 form. These are the numbers
  the SMS and the voice call reach.
- **Let keyholders acknowledge by phone**: on, if you want the phone acknowledge
  flow in section 4.

That is the whole outbound path. Without the acknowledge flow, keyholders are
told but cannot stop the ladder from the phone, so at least one keyholder needs
Home Assistant to acknowledge.

## 4. Inbound, so a phone can acknowledge

A keyholder presses **1** on the voice call, or replies **ACK** to the SMS, and
the ladder stops. Both reach a webhook this integration registers. Twilio will
only call a URL whose certificate it trusts, so there are two ways to give it
one.

### Either give Home Assistant a trusted certificate

A Cloudflare Tunnel, a reverse proxy such as Caddy, or Nabu Casa Cloud all give
Home Assistant a publicly trusted HTTPS address. Set **External URL** to that
address and leave the relay option empty. The integration then uses the Home
Assistant webhook directly. Its address is written to the log at startup when
phone acknowledgement is on.

### Or use a relay, keeping the self signed certificate

If Home Assistant stays on a self signed certificate, put a small trusted relay
in front. Twilio talks to the relay, which forwards to Home Assistant and
tolerates the certificate Twilio would refuse. A Twilio Function is a good
relay, since Twilio already trusts it.

1. In the Twilio Console open **Functions and Assets**, **Services**, and
   create a service.
2. Under **Environment Variables** add:
   - `HA_HOST`, the public address of Home Assistant, for example the Azure
     public IP
   - `HA_PORT`, usually `8123`
   - `HA_WEBHOOK_ID`, the id from the Home Assistant log
3. Add a Function, for example at path `/ack`, with this code:

```javascript
exports.handler = function (context, event, callback) {
  const https = require("https");
  const body = new URLSearchParams(event).toString();
  const req = https.request(
    {
      hostname: context.HA_HOST,
      port: context.HA_PORT || 8123,
      path: "/api/webhook/" + context.HA_WEBHOOK_ID,
      method: "POST",
      headers: {
        "Content-Type": "application/x-www-form-urlencoded",
        "Content-Length": Buffer.byteLength(body),
      },
      rejectUnauthorized: false, // tolerate the self signed certificate
    },
    (res) => {
      let data = "";
      res.on("data", (c) => (data += c));
      res.on("end", () => {
        const response = new Twilio.Response();
        response.appendHeader("Content-Type", "text/xml");
        response.setBody(data);
        callback(null, response);
      });
    }
  );
  req.on("error", (e) => callback(e));
  req.write(body);
  req.end();
};
```

4. Set the Function visibility to **Protected**, so only genuine Twilio requests
   reach it, and **Deploy**. Note the Function URL, for example
   `https://ack-1234.twil.io/ack`.
5. Put that URL in the **Acknowledgement relay URL** option in the integration.
   The voice call now fetches its script from the relay.
6. Allow the Home Assistant port inbound from Twilio in the Azure network
   security group, since the relay reaches Home Assistant on that port.

## 5. Wire the Twilio number for SMS replies

The voice call needs nothing on the number, because each outbound call carries
its own script. For SMS replies:

1. In the Console open **Phone Numbers**, **Manage**, **Active numbers**, and
   open your number.
2. Under **Messaging**, set **A message comes in** to **Webhook**, method
   **HTTP POST**, and the URL to the relay URL from section 4, or to the Home
   Assistant webhook address if you gave it a trusted certificate.
3. Save.

## 6. On each keyholder phone

- Save the Twilio number as a contact.
- Set it as an **emergency bypass** on iOS or a **priority** contact on Android,
  so a call from it rings at three in the morning even on silent.

## 7. Test it

- Press **Test alerts** and let the ladder run all the way to the voice call.
- Answer, listen, and press **1**. The ladder should stop and everyone should
  get an acknowledged notice naming who responded.
- Send a fresh test, and this time reply **ACK** to the SMS. It should stop too.

## Notes

- The words that acknowledge over SMS are `ACK`, `ACKNOWLEDGE`, `OK`, `YES` and
  `1`. `STOP` is deliberately not one of them, because Twilio treats it as a
  carrier opt out and never delivers it.
- Costs are per message and per minute at Twilio's standard rates. Repeating
  voice calls in a long ladder cost more, so tune the number of rounds to taste.
- This is supplementary awareness, not a signalling path. It does not replace
  the panel's own monitored route to an alarm receiving centre.

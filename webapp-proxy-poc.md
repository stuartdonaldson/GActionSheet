Here is the complete, unified proof-of-concept specification combined into a single, cohesive Markdown document that you can save as a single file (e.g., `poc-dual-architecture.md`) to build and verify your setup.

---

```markdown
# POC: Single Script Dual-Architecture Verification

This specification details how a single Apps Script project can handle standard container-bound spreadsheet logic while simultaneously serving a Google Docs Workspace Add-on using only a single Google Cloud Platform (GCP) footprint.

---

## 🛠️ Phase 1: Environment & File Prep

1. Create a brand new Google Sheet named `POC Master Ledger`.
2. Open **Extensions > Apps Script** from inside that sheet. This creates a **Container-Bound Script**.
3. In the Apps Script project settings (Gear Icon), link this script to your **Single standard GCP Project**.
4. In that same GCP project, ensure the **Google Workspace Add-ons API** is enabled.

---

## 📄 Phase 2: Manifest Configuration (`appsscript.json`)

Toggle the file view in your Apps Script editor to show `appsscript.json` and overwrite it with the following configuration. This registers both the spreadsheet permissions and the Google Docs add-on context:

```json
{
  "timeZone": "America/New_York",
  "exceptionLogging": "STACKDRIVER",
  "runtimeVersion": "V8",
  "oauthScopes": [
    "[https://www.googleapis.com/auth/spreadsheets](https://www.googleapis.com/auth/spreadsheets)",
    "[https://www.googleapis.com/auth/documents.currentonly](https://www.googleapis.com/auth/documents.currentonly)",
    "[https://www.googleapis.com/auth/script.external_request](https://www.googleapis.com/auth/script.external_request)"
  ],
  "addOns": {
    "common": {
      "name": "POC Dual Tool",
      "logoUrl": "[https://drive.google.com/uc?export=view&id=1B_g88pREp23W0X9E7X-F6eX8HlY-D_bM](https://drive.google.com/uc?export=view&id=1B_g88pREp23W0X9E7X-F6eX8HlY-D_bM)", 
      "homepageTrigger": { "runFunction": "buildDocsCard" }
    },
    "docs": {
      "homepageTrigger": { "runFunction": "buildDocsCard" }
    }
  }
}

```

---

## 💻 Phase 3: The Code Blueprint (`Code.gs`)

Replace your script code with this structure. It establishes a native sheet UI macro alongside a Docs card UI that routes inputs through a self-referencing execution webhook:

```javascript
// ==========================================
// ACTION 1: CONTAINER-BOUND SPREADSHEET MACRO
// ==========================================
function onOpen(e) {
  SpreadsheetApp.getUi()
    .createMenu('POC Admin')
    .addItem('Test Sheet Macro', 'runSheetMacro')
    .addToUi();
}

function runSheetMacro() {
  SpreadsheetApp.getActiveSpreadsheet().getActiveSheet()
    .appendRow([new Date(), "Admin Profile", "Executed Container Macro Directly"]);
}

// ==========================================
// ACTION 2: GOOGLE DOCS WORKSPACE ADD-ON UI
// ==========================================
function buildDocsCard(e) {
  const card = CardService.newCardBuilder();
  card.setHeader(CardService.newCardHeader().setTitle("POC Log Transfer"));
  
  const textInput = CardService.newTextInput()
    .setFieldName("poc_input")
    .setTitle("Type Verification Message");
    
  const button = CardService.newTextButton()
    .setText("Submit via Webapp Webhook")
    .setOnClickAction(CardService.newAction().setFunctionName("relayDataToSheet"));

  const section = CardService.newCardSection().addWidget(textInput).addWidget(button);
  return card.addSection(section).build();
}

function relayDataToSheet(e) {
  const userInput = e.formInput.poc_input;
  const userEmail = Session.getActiveUser().getEmail();
  
  // DYNAMIC URL LOOKUP: Fetches the URL you will deploy in Phase 4
  const webAppUrl = PropertiesService.getScriptProperties().getProperty("WEBAPP_URL");
  
  if (!webAppUrl) {
    return CardService.newActionResponseBuilder()
      .setNotification(CardService.newNotification().setText("FAIL: Deploy Web App first & save URL in properties!"))
      .build();
  }

  // Fire outbound payload. Bob triggers this, but it calls the Webapp running as You.
  UrlFetchApp.fetch(webAppUrl, {
    method: "post",
    contentType: "application/json",
    payload: JSON.stringify({ email: userEmail, message: userInput })
  });

  return CardService.newActionResponseBuilder()
    .setNotification(CardService.newNotification().setText("Success! Data routed via proxy."))
    .build();
}

// ==========================================
// ACTION 3: THE WEBHOOK DATA EXECUTION HUB
// ==========================================
function doPost(e) {
  const payload = JSON.parse(e.postData.contents);
  
  // Because this executes under the deployer's identity (You),
  // it retains native authority to open its own parent container!
  const sheet = SpreadsheetApp.getActiveSpreadsheet().getActiveSheet();
  sheet.appendRow([new Date(), payload.email, payload.message]);
  
  return ContentService.createTextOutput("Processed");
}

```

---

## 🚀 Phase 4: Verification & Deployment Workflow

### 1. Deploy the Authorization Proxy (Web App)

1. Inside the script editor, click **Deploy > New Deployment**.
2. Click the gear icon next to "Select type" and select **Web app**.
3. Configure the permissions explicitly:
* **Execute as:** `Me (your-admin-email@org.org)`
* **Who has access:** `Anyone within [Your Organization]`


4. Click **Deploy** and authorize the access requirements.
5. **CRITICAL STEP:** Copy the generated **Web App URL**. Go to **Project Settings > Script Properties**, create a property named `WEBAPP_URL`, and paste that link.

### 2. Install the Add-on Test Build

1. In the editor, click **Deploy > Test deployments**.
2. Click **Install** next to the Add-on row configuration.

---

## 🧪 Phase 5: Run the Proof-of-Concept Tests

### Test 1: Verify the Container-Bound Layer

* Refresh your `POC Master Ledger` Google Sheet.
* Click **POC Admin > Test Sheet Macro** from the top menu dropdown.
* *Expected Result:* A new row appends locally in the sheet instantly.

### Test 2: Verify the Add-on Cross-File Authorization Bypass

* Share the root Apps Script project with a tester account (e.g., `Bob`) as an **Editor** (required for test builds).
* **Crucial:** Do **NOT** share the `POC Master Ledger` Google Sheet with Bob. Bob must have zero direct access to it.
* Have Bob log into a separate browser profile, open a completely blank **Google Doc**, open the right side-panel (reveal it using the `<` icon in the bottom right corner if hidden), and click your add-on icon.
* Have Bob type a string in the card widget and click **Submit via Webapp Webhook**.
* *Expected Result:* The notification reads "Success!" and you will see Bob's input and email populate the spreadsheet grid in real-time, proving that the single script successfully bridged the security boundary using a single GCP project footprint.

```
---

```
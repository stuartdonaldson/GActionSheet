/**
 * AtddContracts.js
 *
 * Machine-readable contract for the ATDD scenario-harness ↔ GAS boundary.
 *
 * SCOPE: these entry points exist ONLY to let the Python scenario harness drive
 * an end-to-end journey. They are NOT part of the production application surface
 * (no production add-on, trigger, or menu path invokes them). Production-consumed
 * contracts live in ContractSchema.js. Routes that run in the WebApp purely to
 * support testing (but operate on production data/behaviour) live in
 * ContractSchema.js `webApp.testRouteNames`; the journey-session lifecycle below
 * is exclusively an ATDD concern, so it lives here.
 *
 * Human-readable semantics live in docs/DESIGN.md §ATDD Journey Pre-Code Contract.
 * Pre-code contract for epic GTaskSheet-5vwu (bead .2); implemented by .8;
 * exported to JSON + consumed by Python in .3.
 *
 * Decisions consumed (docs/atdd/atdd-lifecycle.md §16.11):
 *   #1 empty-create journey doc; #4 sync drains the message queue before responding.
 */

var ATDD_CONTRACTS = Object.freeze({

  // doPost actions that exist solely for the ATDD harness. Each is dispatched by
  // WebApp.doPost on `payload.action` exactly like a production route, but is
  // gated to the test token and never reached by the production application.
  sessionRouteNames: Object.freeze([
    'begin_journey_session',
    'end_journey_session'
  ]),

  // Naming + placement contract for the isolated journey document (§16.11 #1, §15).
  journeyDoc: Object.freeze({
    // strftime-style; {hex} = 4 lowercase hex chars (secrets.token_hex(2)).
    namePattern: 'GActionSheet-Test-journey-{YYYYMMDD}-{hex}',
    createVia: 'DocumentApp.create',          // never a clone of a template (§16.11 #1)
    folder: 'same Drive folder as the test ActionSheet'
  }),

  messages: Object.freeze({

    // begin_journey_session — create a guaranteed-clean empty journey doc.
    //   Entry point     : doPost { action } dispatch (WebApp.doPost)
    //   Completion signal: synchronous JSON response carrying the new docId
    //                      (the doc is fully created + saved before the response).
    begin_journey_session: Object.freeze({
      request:  Object.freeze(['action', 'testToken']),
      response: Object.freeze(['ok', 'docId', 'docName', 'docUrl']),
      completionSignal: 'synchronous response; docId present'
    }),

    // end_journey_session — trash the journey doc at teardown.
    //   Completion signal: synchronous JSON response { ok:true } after the doc is trashed.
    end_journey_session: Object.freeze({
      request:  Object.freeze(['action', 'testToken', 'docId']),
      response: Object.freeze(['ok']),
      completionSignal: 'synchronous response { ok:true }'
    })
  })
});

/**
 * SmartGarbage AI Chatbot — Free, rule-based, no external API needed.
 * Answers citizen questions about schedules, complaints, payments, and more.
 * Runs entirely in the browser — zero server cost.
 */
(function () {
  'use strict';

  const FAQ_DB = [
    // Schedule queries
    { q: /schedule|collection|pickup|garbage.*time|when.*collect/i, a: 'Collection schedules vary by ward. Check your ward\'s schedule at /schedule — no login needed. Most wards have morning collections between 6-9 AM.' },
    { q: /which.*ward|my.*ward|ward.*name/i, a: 'We serve 5 wards: MVGR College Area, Junction, RTC Colony, Ramalayam Street, and Sai Nagar. Check /schedule for your ward\'s timetable.' },
    { q: /today.*schedule|today.*collection/i, a: 'Today\'s schedule is on /schedule — select your ward and see the exact pickup time. No login required.' },

    // Complaint queries
    { q: /report|complaint|missed.*pickup|not.*collect|overflow/i, a: 'File a complaint at /report — it\'s free, no login needed. You can add a photo and GPS location. You\'ll get a tracking link instantly.' },
    { q: /track|status|follow.*up|where.*complaint/i, a: 'Track your complaint at /register — log in to see your dashboard with real-time status updates. Or use the tracking link sent to your phone/email.' },
    { q: /how.*long|resolution.*time|when.*resolved/i, a: 'Average resolution time is shown on the Impact Dashboard (/impact). Most complaints are resolved within 24-48 hours.' },

    // Payment queries
    { q: /pay|bill|invoice|PAYT|payment/i, a: 'PAYT (Pay-As-You-Throw) billing is for bulk waste generators. Regular residents use the portal for free. Check /register for your billing dashboard.' },
    { q: /UPI|upi|pay.*app/i, a: 'UPI payments are available on the payment page. Click "Pay via UPI" to open your preferred UPI app. No card or net-banking needed.' },
    { q: /fee|cost|charge|free/i, a: 'The SmartGarbage portal is completely FREE for residents. No registration fee, no usage charge. PAYT billing applies only to bulk waste generators.' },

    // Green Points
    { q: /green.*point|earn|redeem|reward/i, a: 'Green Points are earned by filing complaints (15 points each) and maintaining segregation compliance. Redeem for local vouchers and tax discounts at /register.' },
    { q: /segregation|separate|waste.*type/i, a: 'Keep dry recyclables (plastic, paper, metal) separate from wet food waste. Two bags, two categories — helps recycle 40% more waste.' },

    // General
    { q: /contact|phone|helpline|hotline/i, a: 'Grievance hotline: 1800-119-9111 (toll-free). Visit /contact for email and office address.' },
    { q: /about|who.*run|operator|government/i, a: 'SmartGarbage is operated by the Directorate of Waste Management & Sanitation, Chintalavalasa Gram Panchayat. See /about for details.' },
    { q: /privacy|data|personal/i, a: 'We collect minimal data as per DPDP Act 2023. See /privacy for our full privacy policy.' },
    { q: /language|telugu|english|hindi/i, a: 'The portal supports English and Telugu (తెలుగు). Switch languages using the flag icon in the top navigation.' },
    { q: /impact|statistic|metric|dashboard/i, a: 'Live impact metrics are on /impact — complaints resolved, recycling rate, CO2 saved, ward rankings, and community engagement.' },
    { q: /bin|smart.*bin|sensor|IoT/i, a: 'Smart bins with IoT sensors monitor fill levels in real-time. Check /transparency for live bin status across all wards.' },
    { q: /hello|hi|hey|namaste/i, a: 'Namaste! 🙏 I\'m SmartGarbage assistant. I can help with schedules, complaints, payments, Green Points, and more. What do you need?' },
    { q: /thank|thanks/i, a: 'You\'re welcome! 😊 Remember, keeping our community clean starts with each of us. File a report anytime at /report.' },
  ];

  const FALLBACK = 'I can help with schedules, complaints, payments, Green Points, and more. Try asking:\n• "What\'s my collection schedule?"\n• "How do I report a missed pickup?"\n• "What are Green Points?"\n• "Is the portal free?"';

  function findAnswer(input) {
    const text = input.trim().toLowerCase();
    if (!text) return FALLBACK;
    for (const item of FAQ_DB) {
      if (item.q.test(text)) return item.a;
    }
    return FALLBACK;
  }

  // DOM setup
  function init() {
    // Create chatbot HTML
    const container = document.createElement('div');
    container.id = 'sg-chatbot';
    container.innerHTML = `
      <button id="sg-chat-toggle" aria-label="Open chat assistant" title="Ask SmartGarbage Assistant">
        💬
      </button>
      <div id="sg-chat-window" class="d-none" role="dialog" aria-label="SmartGarbage Chat Assistant">
        <div class="sg-chat-header">
          <span>🤖 SmartGarbage Assistant</span>
          <button id="sg-chat-close" aria-label="Close chat">&times;</button>
        </div>
        <div id="sg-chat-messages" class="sg-chat-messages">
          <div class="sg-chat-msg sg-chat-bot">
            Namaste! 🙏 I can help with schedules, complaints, payments, and Green Points. What do you need?
          </div>
        </div>
        <div class="sg-chat-input-row">
          <input type="text" id="sg-chat-input" placeholder="Type your question..." aria-label="Type your question" autocomplete="off">
          <button id="sg-chat-send" aria-label="Send message">→</button>
        </div>
      </div>
    `;
    document.body.appendChild(container);

    // Event listeners
    const toggle = document.getElementById('sg-chat-toggle');
    const win = document.getElementById('sg-chat-window');
    const close = document.getElementById('sg-chat-close');
    const input = document.getElementById('sg-chat-input');
    const send = document.getElementById('sg-chat-send');
    const msgs = document.getElementById('sg-chat-messages');

    function addMessage(text, isBot) {
      const div = document.createElement('div');
      div.className = 'sg-chat-msg ' + (isBot ? 'sg-chat-bot' : 'sg-chat-user');
      div.textContent = text;
      msgs.appendChild(div);
      msgs.scrollTop = msgs.scrollHeight;
    }

    function handleSend() {
      const text = input.value.trim();
      if (!text) return;
      addMessage(text, false);
      input.value = '';
      setTimeout(() => addMessage(findAnswer(text), true), 300);
    }

    toggle.addEventListener('click', () => {
      win.classList.toggle('d-none');
      toggle.classList.toggle('active');
      if (!win.classList.contains('d-none')) input.focus();
    });

    close.addEventListener('click', () => {
      win.classList.add('d-none');
      toggle.classList.remove('active');
    });

    send.addEventListener('click', handleSend);
    input.addEventListener('keydown', (e) => {
      if (e.key === 'Enter') handleSend();
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();

document.addEventListener("DOMContentLoaded", function () {
  const tg = window.Telegram ? window.Telegram.WebApp : null;
  if (tg) {
    try {
      tg.ready();
      tg.expand();
      document.body.classList.add("telegram-theme");
    } catch (e) {
      console.warn("Telegram WebApp init error", e);
    }
  }

  let currentData = null;

  function formatMoney(amount) {
    const num = Math.round(Number(amount) || 0);
    return num.toLocaleString("ru-RU") + " ₽";
  }

  function formatDate(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const day = String(d.getDate()).padStart(2, "0");
    const month = String(d.getMonth() + 1).padStart(2, "0");
    return `${day}.${month}`;
  }

  // Tab Navigation
  const navItems = document.querySelectorAll(".nav-item");
  const tabPages = document.querySelectorAll(".tab-page");

  navItems.forEach(item => {
    item.addEventListener("click", function() {
      const targetTab = this.getAttribute("data-tab");
      navItems.forEach(n => {
        n.classList.remove("active");
        n.style.color = "var(--text-muted)";
      });
      this.classList.add("active");
      this.style.color = "var(--accent-blue)";

      tabPages.forEach(p => p.style.display = "none");
      const activePage = document.getElementById("tab-" + targetTab);
      if (activePage) activePage.style.display = "block";
    });
  });

  async function loadSummary() {
    try {
      const headers = {};
      if (tg && tg.initData) {
        headers["telegram-web-app-init-data"] = tg.initData;
      }

      const res = await fetch("/api/summary", { headers });
      if (!res.ok) {
        document.getElementById("content").innerHTML = `<div class="loading">Ошибка загрузки данных (${res.status})</div>`;
        return;
      }

      currentData = await res.json();
      renderApp(currentData);
      populateAccountInputs(currentData);
    } catch (err) {
      console.error(err);
      document.getElementById("content").innerHTML = `<div class="loading">Не удалось связаться с сервером</div>`;
    }
  }

  function renderApp(data) {
    // Balances
    const totalCap = Number(data.total_capital) || Number(data.balance) || 1;
    document.getElementById("total-capital").textContent = formatMoney(data.total_capital || data.balance);
    document.getElementById("total-balance").textContent = formatMoney(data.balance);

    document.getElementById("month-income").textContent = "+" + formatMoney(data.income_month);
    document.getElementById("month-expense").textContent = "-" + formatMoney(data.expense_month);
    document.getElementById("free-cash-flow").textContent = formatMoney(data.free_cash_flow);
    document.getElementById("savings-rate").textContent = (data.savings_rate || 0).toFixed(1) + "%";

    // Financial Runway
    const runwayVal = document.getElementById("runway-value");
    if (data.financial_runway_months >= 99) {
      runwayVal.textContent = "Безгранично 🎉";
    } else {
      runwayVal.textContent = `${data.financial_runway_months.toFixed(1)} мес. трат`;
      runwayVal.style.color = data.financial_runway_months < 3 ? "var(--accent-red)" : "var(--accent-green)";
    }

    // Asset Allocation Bar
    if (data.accounts && data.accounts.length > 0) {
      const mainAcc = data.accounts.find(a => a.type === "main");
      const savAcc = data.accounts.find(a => a.type === "savings" && a.enabled);
      const depAcc = data.accounts.find(a => a.type === "deposit" && a.enabled);

      const mainBal = mainAcc ? Math.max(0, Number(mainAcc.balance)) : 0;
      const savBal = savAcc ? Math.max(0, Number(savAcc.balance)) : 0;
      const depBal = depAcc ? Math.max(0, Number(depAcc.balance)) : 0;

      const mainPct = Math.round((mainBal / totalCap) * 100);
      const savPct = Math.round((savBal / totalCap) * 100);
      const depPct = Math.round((depBal / totalCap) * 100);

      document.getElementById("alloc-main").style.width = mainPct + "%";
      document.getElementById("alloc-savings").style.width = savPct + "%";
      document.getElementById("alloc-deposit").style.width = depPct + "%";
    }

    // Accounts breakdown
    const accContainer = document.getElementById("accounts-list");
    accContainer.innerHTML = "";
    if (data.accounts && data.accounts.length > 0) {
      const activeAccounts = data.accounts.filter(a => a.enabled);
      if (activeAccounts.length > 0) {
        activeAccounts.forEach(acc => {
          const item = document.createElement("div");
          item.className = "cat-item";
          let subText = "";
          if (acc.type === "savings") {
            subText = acc.apy > 0 ? `Ставка ${acc.apy}% APY • ~+${formatMoney(acc.monthly_interest)}/мес` : "Без процентов";
          } else if (acc.type === "deposit") {
            subText = acc.apy > 0 ? `Ставка ${acc.apy}% APY на ${acc.months} мес • На выходе ~${formatMoney(acc.projected_total)}` : "Без процента";
          } else {
            subText = "Карта / Наличные";
          }

          item.innerHTML = `
            <div class="cat-info">
              <span class="cat-name">${acc.name}</span>
              <span class="cat-meta">${subText}</span>
            </div>
            <span class="tx-amount" style="color: var(--text-main);">${formatMoney(acc.balance)}</span>
          `;
          accContainer.appendChild(item);
        });

        if (data.total_passive_income_monthly > 0) {
          const passiveItem = document.createElement("div");
          passiveItem.className = "cat-meta";
          passiveItem.style.padding = "6px 8px";
          passiveItem.style.color = "var(--accent-green)";
          passiveItem.style.fontWeight = "600";
          passiveItem.textContent = `💸 Пассивный доход по процентам: ~+${formatMoney(data.total_passive_income_monthly)}/мес`;
          accContainer.appendChild(passiveItem);
        }
      } else {
        accContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет активных счетов</div>`;
      }
    }

    // Category Budgets
    const budgetsContainer = document.getElementById("budgets-list");
    budgetsContainer.innerHTML = "";
    if (data.category_budgets && data.category_budgets.length > 0) {
      data.category_budgets.forEach(b => {
        const item = document.createElement("div");
        item.className = "goal-card";
        let statusColor = "var(--accent-green)";
        if (b.percentage >= 100) statusColor = "var(--accent-red)";
        else if (b.percentage >= 80) statusColor = "#f59e0b";

        item.innerHTML = `
          <div class="goal-header">
            <span>🏷 ${b.category}</span>
            <span>${formatMoney(b.spent)} / ${formatMoney(b.limit)}</span>
          </div>
          <div class="goal-progress-bar">
            <div class="goal-progress-fill" style="width: ${Math.min(100, b.percentage)}%; background: ${statusColor}"></div>
          </div>
          <div class="goal-meta">
            <span>Потрачено: ${b.percentage.toFixed(0)}%</span>
            <span style="color: ${statusColor}">${b.percentage >= 100 ? '⚠️ Превышен' : 'В норме'}</span>
          </div>
        `;
        budgetsContainer.appendChild(item);
      });
    } else {
      budgetsContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Бюджеты не настроены (перейдите во вкладку «🏦 Счета»)</div>`;
    }

    // Top Categories
    const catContainer = document.getElementById("top-categories");
    catContainer.innerHTML = "";
    if (data.top_expense_categories && data.top_expense_categories.length > 0) {
      data.top_expense_categories.forEach(cat => {
        const item = document.createElement("div");
        item.className = "cat-item";
        item.innerHTML = `
          <div class="cat-info">
            <span class="cat-name">${cat.category}</span>
            <span class="cat-meta">${cat.percentage.toFixed(1)}% от трат за месяц</span>
          </div>
          <span class="tx-amount expense">-${formatMoney(cat.amount)}</span>
        `;
        catContainer.appendChild(item);
      });
    } else {
      catContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет расходов за текущий месяц</div>`;
    }

    // Goals
    const goalsContainer = document.getElementById("goals-list");
    goalsContainer.innerHTML = "";
    if (data.active_goals && data.active_goals.length > 0) {
      data.active_goals.forEach(goal => {
        const item = document.createElement("div");
        item.className = "goal-card";
        item.innerHTML = `
          <div class="goal-header">
            <span>🎯 ${goal.title}</span>
            <span>${formatMoney(goal.current_amount)} / ${formatMoney(goal.target_amount)}</span>
          </div>
          <div class="goal-progress-bar">
            <div class="goal-progress-fill" style="width: ${goal.progress_percentage}%"></div>
          </div>
          <div class="goal-meta">
            <span>Прогресс: ${goal.progress_percentage.toFixed(0)}%</span>
            <span>Статус: ${goal.status === 'done' ? 'Достигнута 🎉' : 'В процессе'}</span>
          </div>
        `;
        goalsContainer.appendChild(item);
      });
    } else {
      goalsContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет активных целей</div>`;
    }

    // Recent Transactions
    const txContainer = document.getElementById("recent-transactions");
    txContainer.innerHTML = "";
    if (data.recent_transactions && data.recent_transactions.length > 0) {
      data.recent_transactions.forEach(tx => {
        const item = document.createElement("div");
        item.className = "tx-item";
        const sign = tx.type === "income" ? "+" : (tx.type === "expense" ? "-" : "");
        const categoryStr = tx.category ? ` • ${tx.category}` : "";

        item.innerHTML = `
          <div class="tx-info">
            <span class="tx-title">${tx.note || tx.category || "Операция"}</span>
            <span class="tx-sub">${formatDate(tx.date)}${categoryStr}</span>
          </div>
          <span class="tx-amount ${tx.type}">${sign}${formatMoney(tx.amount)}</span>
        `;
        txContainer.appendChild(item);
      });
    } else {
      txContainer.innerHTML = `<div class="cat-meta" style="padding: 10px;">Нет операций</div>`;
    }
  }

  function populateAccountInputs(data) {
    if (data && data.accounts) {
      const mainAcc = data.accounts.find(a => a.type === "main");
      const savAcc = data.accounts.find(a => a.type === "savings");
      const depAcc = data.accounts.find(a => a.type === "deposit");

      if (mainAcc) document.getElementById("acc-main-bal").value = mainAcc.balance;
      if (savAcc) {
        document.getElementById("acc-sav-bal").value = savAcc.balance;
        document.getElementById("acc-sav-apy").value = savAcc.apy || 0;
        document.getElementById("acc-sav-enabled").checked = savAcc.enabled;
      }
      if (depAcc) {
        document.getElementById("acc-dep-bal").value = depAcc.balance;
        document.getElementById("acc-dep-apy").value = depAcc.apy || 0;
        document.getElementById("acc-dep-months").value = depAcc.months || 12;
        document.getElementById("acc-dep-enabled").checked = depAcc.enabled;
      }
    }
  }

  // Operation Type Toggle
  let selectedOpType = "expense";
  const opTypeBtns = document.querySelectorAll(".op-type-btn");
  opTypeBtns.forEach(btn => {
    btn.addEventListener("click", function() {
      opTypeBtns.forEach(b => {
        b.style.background = "transparent";
        b.style.color = "var(--text-main)";
        b.classList.remove("active");
      });
      this.classList.add("active");
      selectedOpType = this.getAttribute("data-type");

      const transferSelect = document.getElementById("transfer-accounts-select");
      const catContainer = document.getElementById("category-select-container");

      if (selectedOpType === "transfer") {
        this.style.background = "var(--accent-blue)";
        this.style.color = "white";
        transferSelect.style.display = "block";
        catContainer.style.display = "none";
      } else if (selectedOpType === "income") {
        this.style.background = "var(--accent-green)";
        this.style.color = "white";
        transferSelect.style.display = "none";
        catContainer.style.display = "block";
      } else {
        this.style.background = "var(--accent-red)";
        this.style.color = "white";
        transferSelect.style.display = "none";
        catContainer.style.display = "block";
      }
    });
  });

  // Create Operation
  const submitOpBtn = document.getElementById("submit-op-btn");
  if (submitOpBtn) {
    submitOpBtn.addEventListener("click", async function() {
      const amount = Number(document.getElementById("op-amount").value);
      if (!amount || amount <= 0) {
        alert("Пожалуйста, введите корректную сумму");
        return;
      }

      const payload = {
        type: selectedOpType,
        amount: amount,
        category: selectedOpType === "transfer" ? "Переводы" : document.getElementById("op-category").value,
        note: document.getElementById("op-note").value,
        target_account: document.getElementById("op-target-account").value
      };

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/operations", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          document.getElementById("op-amount").value = "";
          document.getElementById("op-note").value = "";
          alert("✅ Операция успешно сохранена!");
          loadSummary();
        } else {
          alert("Ошибка при сохранении операции");
        }
      } catch (err) {
        console.error(err);
        alert("Ошибка связи с сервером");
      }
    });
  }

  // QR Code File Upload
  const uploadQrBtn = document.getElementById("upload-qr-btn");
  const qrFileInput = document.getElementById("qr-file-input");
  const qrStatus = document.getElementById("qr-scan-status");

  if (uploadQrBtn && qrFileInput) {
    uploadQrBtn.addEventListener("click", () => qrFileInput.click());
    qrFileInput.addEventListener("change", async function() {
      if (!this.files || !this.files[0]) return;
      const file = this.files[0];
      qrStatus.textContent = "⏳ Сканирование QR-кода...";

      const formData = new FormData();
      formData.append("file", file);

      try {
        const headers = {};
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/scan_qr", {
          method: "POST",
          headers: headers,
          body: formData
        });

        const data = await res.json();
        if (data.success) {
          qrStatus.innerHTML = `✅ <strong style="color: var(--accent-green)">Считан чек на ${data.amount} ₽!</strong>`;
          document.getElementById("op-amount").value = data.amount;
          document.getElementById("op-note").value = data.note;
        } else {
          qrStatus.textContent = "❌ " + (data.message || "Не удалось найти QR-код чека на снимке");
        }
      } catch (err) {
        console.error(err);
        qrStatus.textContent = "❌ Ошибка отправки фото";
      }
    });
  }

  // Save Accounts in Tab 3
  const saveAccTabBtn = document.getElementById("save-accounts-tab-btn");
  if (saveAccTabBtn) {
    saveAccTabBtn.addEventListener("click", async function() {
      const payload = {
        main_balance: Number(document.getElementById("acc-main-bal").value) || 0,
        savings_balance: Number(document.getElementById("acc-sav-bal").value) || 0,
        savings_apy: Number(document.getElementById("acc-sav-apy").value) || 0,
        savings_enabled: Boolean(document.getElementById("acc-sav-enabled").checked),
        deposit_balance: Number(document.getElementById("acc-dep-bal").value) || 0,
        deposit_apy: Number(document.getElementById("acc-dep-apy").value) || 0,
        deposit_months: Number(document.getElementById("acc-dep-months").value) || 12,
        deposit_enabled: Boolean(document.getElementById("acc-dep-enabled").checked)
      };

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/accounts", {
          method: "POST",
          headers: headers,
          body: JSON.stringify(payload)
        });

        if (res.ok) {
          alert("✅ Параметры счетов сохранены!");
          loadSummary();
        } else {
          alert("Ошибка сохранения счетов");
        }
      } catch (err) {
        console.error(err);
        alert("Не удалось сохранить счета");
      }
    });
  }

  // Save Category Budget Limit
  const saveBudgetBtn = document.getElementById("save-budget-btn");
  if (saveBudgetBtn) {
    saveBudgetBtn.addEventListener("click", async function() {
      const cat = document.getElementById("budget-cat-select").value;
      const limit = Number(document.getElementById("budget-limit-input").value);
      if (!limit || limit <= 0) {
        alert("Введите сумму лимита больше 0");
        return;
      }

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/budgets", {
          method: "POST",
          headers: headers,
          body: JSON.stringify({ category: cat, limit: limit })
        });

        if (res.ok) {
          alert(`✅ Лимит для «${cat}» сохранен!`);
          document.getElementById("budget-limit-input").value = "";
          loadSummary();
        } else {
          alert("Ошибка сохранения лимита");
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // AI Chat Assistant
  const chatFeed = document.getElementById("ai-chat-feed");
  const chatInput = document.getElementById("ai-chat-input");
  const sendAiBtn = document.getElementById("send-ai-btn");
  const chipBtns = document.querySelectorAll(".ai-chip-btn");

  async function sendAiQuestion(questionText) {
    if (!questionText.trim()) return;

    const userMsg = document.createElement("div");
    userMsg.className = "chat-msg user";
    userMsg.textContent = questionText;
    chatFeed.appendChild(userMsg);
    chatFeed.scrollTop = chatFeed.scrollHeight;

    chatInput.value = "";

    const loadingAi = document.createElement("div");
    loadingAi.className = "chat-msg ai";
    loadingAi.textContent = "🤖 Рассчитываю и анализирую...";
    chatFeed.appendChild(loadingAi);
    chatFeed.scrollTop = chatFeed.scrollHeight;

    try {
      const headers = { "Content-Type": "application/json" };
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/chat", {
        method: "POST",
        headers: headers,
        body: JSON.stringify({ question: questionText })
      });

      if (res.ok) {
        const data = await res.json();
        loadingAi.innerHTML = data.answer;
      } else {
        loadingAi.textContent = "❌ Не удалось получить ответ от ИИ";
      }
    } catch (err) {
        console.error(err);
        loadingAi.textContent = "❌ Ошибка соединения с ИИ сервисом";
    }
    chatFeed.scrollTop = chatFeed.scrollHeight;
  }

  if (sendAiBtn && chatInput) {
    sendAiBtn.addEventListener("click", () => sendAiQuestion(chatInput.value));
    chatInput.addEventListener("keypress", (e) => {
      if (e.key === "Enter") sendAiQuestion(chatInput.value);
    });
  }

  // --- Trends Line Chart & Author Split ---
  let trendChartInstance = null;

  async function loadTrendsChart() {
    const canvas = document.getElementById("expense-trend-chart");
    if (!canvas || !window.Chart) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/analytics/trends?period=90", { headers });
      if (!res.ok) return;

      const data = await res.json();
      if (trendChartInstance) trendChartInstance.destroy();

      const ctx = canvas.getContext("2d");
      trendChartInstance = new Chart(ctx, {
        type: "line",
        data: {
          labels: data.dates.map(d => formatDate(d)),
          datasets: [{
            label: "Расходы (₽)",
            data: data.amounts,
            borderColor: "#3b82f6",
            backgroundColor: "rgba(59, 130, 246, 0.15)",
            borderWidth: 2,
            tension: 0.3,
            fill: true,
            pointRadius: 2
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { ticks: { color: "#94a3b8", fontSize: 10 } },
            y: { ticks: { color: "#94a3b8", fontSize: 10 } }
          }
        }
      });
    } catch (err) {
      console.error("Chart load error", err);
    }
  }

  async function loadAuthorsBreakdown() {
    const container = document.getElementById("authors-breakdown-list");
    if (!container) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/analytics/authors?period=30", { headers });
      if (!res.ok) return;

      const items = await res.json();
      if (!items || items.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); font-size: 0.85rem;">Нет трат за текущий период</div>';
        return;
      }

      container.innerHTML = items.map(item => `
        <div style="margin-bottom: 8px;">
          <div style="display: flex; justify-content: space-between; font-size: 0.85rem; margin-bottom: 4px;">
            <span>👤 <strong>${item.author_name}</strong></span>
            <span><strong>${formatMoney(item.amount)}</strong> (${item.percentage}%)</span>
          </div>
          <div style="height: 6px; background: rgba(255,255,255,0.1); border-radius: 4px; overflow: hidden;">
            <div style="width: ${item.percentage}%; height: 100%; background: var(--accent-blue);"></div>
          </div>
        </div>
      `).join("");
    } catch (err) {
      console.error("Authors breakdown error", err);
    }
  }

  // --- Subscriptions Tab ---
  async function loadSubscriptions() {
    const container = document.getElementById("subs-list");
    if (!container) return;

    try {
      const headers = {};
      if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

      const res = await fetch("/api/subscriptions", { headers });
      if (!res.ok) return;

      const data = await res.json();
      document.getElementById("subs-total-monthly").textContent = formatMoney(data.total_monthly);
      document.getElementById("subs-total-yearly").textContent = formatMoney(data.total_yearly);

      if (!data.subscriptions || data.subscriptions.length === 0) {
        container.innerHTML = '<div style="color: var(--text-muted); padding: 12px; text-align: center;">Подписок пока нет</div>';
        return;
      }

      container.innerHTML = data.subscriptions.map(s => {
        const periodStr = s.period === "monthly" ? "мес" : (s.period === "yearly" ? "год" : "кв");
        const nextBillingStr = s.next_billing ? formatDate(s.next_billing) : `день ${s.billing_day}`;
        return `
          <div style="background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; padding: 14px; margin-bottom: 10px; display: flex; justify-content: space-between; align-items: center;">
            <div>
              <div style="font-weight: 700; font-size: 0.95rem;">${s.name}</div>
              <div style="font-size: 0.78rem; color: var(--text-muted);">📅 След. списание: ${nextBillingStr}</div>
            </div>
            <div style="text-align: right; display: flex; align-items: center; gap: 10px;">
              <div>
                <div style="font-weight: 800; color: var(--accent-red);">${formatMoney(s.amount)}/${periodStr}</div>
              </div>
              <button class="delete-sub-btn" data-id="${s.id}" style="background: rgba(239, 68, 68, 0.15); border: none; color: var(--accent-red); padding: 6px 10px; border-radius: 6px; cursor: pointer;">🗑</button>
            </div>
          </div>
        `;
      }).join("");

      document.querySelectorAll(".delete-sub-btn").forEach(btn => {
        btn.addEventListener("click", async function() {
          const subId = this.getAttribute("data-id");
          if (!confirm("Удалить эту подписку?")) return;

          try {
            const h = { "Content-Type": "application/json" };
            if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;

            const dRes = await fetch(`/api/subscriptions/${subId}`, { method: "DELETE", headers: h });
            if (dRes.ok) loadSubscriptions();
          } catch (e) { console.error(e); }
        });
      });

    } catch (err) {
      console.error("Load subscriptions error", err);
    }
  }

  // Toggle Add Subscription Form
  const btnShowAddSub = document.getElementById("btn-show-add-sub");
  const addSubFormContainer = document.getElementById("add-sub-form-container");
  if (btnShowAddSub && addSubFormContainer) {
    btnShowAddSub.addEventListener("click", () => {
      addSubFormContainer.style.display = addSubFormContainer.style.display === "none" ? "block" : "none";
    });
  }

  // Save Subscription
  const btnSaveSub = document.getElementById("btn-save-sub");
  if (btnSaveSub) {
    btnSaveSub.addEventListener("click", async () => {
      const name = document.getElementById("sub-name-input").value.trim();
      const amount = parseFloat(document.getElementById("sub-amount-input").value) || 0;
      const period = document.getElementById("sub-period-select").value;
      const billing_day = parseInt(document.getElementById("sub-day-input").value) || 1;

      if (!name || amount <= 0) {
        alert("Заполните название и сумму подписки");
        return;
      }

      try {
        const headers = { "Content-Type": "application/json" };
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/subscriptions", {
          method: "POST",
          headers,
          body: JSON.stringify({ name, amount, period, billing_day, category: "Подписки" })
        });

        if (res.ok) {
          alert("✅ Подписка добавлена!");
          document.getElementById("sub-name-input").value = "";
          document.getElementById("sub-amount-input").value = "";
          addSubFormContainer.style.display = "none";
          loadSubscriptions();
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // Autodetect Subscriptions Button
  const btnAutodetectSubs = document.getElementById("btn-autodetect-subs");
  if (btnAutodetectSubs) {
    btnAutodetectSubs.addEventListener("click", async () => {
      try {
        const headers = {};
        if (tg && tg.initData) headers["telegram-web-app-init-data"] = tg.initData;

        const res = await fetch("/api/subscriptions/autodetect", { headers });
        if (res.ok) {
          const data = await res.json();
          if (!data.detected || data.detected.length === 0) {
            alert("Повторяющихся подписок в истории трат не найдено.");
            return;
          }
          const msg = data.detected.map(d => `• ${d.name}: ${d.amount} ₽ (день ${d.suggested_billing_day})`).join("\n");
          if (confirm(`Найдены кандидаты в подписки:\n\n${msg}\n\nДобавить их?`)) {
            for (const sub of data.detected) {
              const h = { "Content-Type": "application/json" };
              if (tg && tg.initData) h["telegram-web-app-init-data"] = tg.initData;
              await fetch("/api/subscriptions", {
                method: "POST",
                headers: h,
                body: JSON.stringify({
                  name: sub.name,
                  amount: sub.amount,
                  period: "monthly",
                  billing_day: sub.suggested_billing_day,
                  category: "Подписки"
                })
              });
            }
            loadSubscriptions();
          }
        }
      } catch (err) {
        console.error(err);
      }
    });
  }

  // Check URL Hash for deep linking
  if (window.location.hash === "#subs") {
    const subNavBtn = document.querySelector('.nav-item[data-tab="subs"]');
    if (subNavBtn) subNavBtn.click();
  }

  loadSummary();
  loadTrendsChart();
  loadAuthorsBreakdown();
  loadSubscriptions();
});

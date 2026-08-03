# Plan: Advanced Web App Improvements

We will add three highly engaging, premium, and interactive financial tools to the Web App interface:
1. 📅 **Interactive Financial Calendar** inside the **Subscriptions tab** (visually lists upcoming bills on a monthly grid).
2. 🏆 **Compound Interest Goal Planner** inside the **Accounts tab** (featuring sliders and a Chart.js visualization of compounding growth).
3. 💡 **Savings Challenges** inside the **Profile tab** (fully gamified section tracking progress of 52-week challenge and daily habit limits).

---

## Proposed Changes

### Frontend Integration

#### [MODIFY] [index.html](file:///a:/Dev/our-moneys/app/web/templates/index.html)
- **Tab: Subscriptions (`#tab-subs`)**:
  - Add a beautiful container `#sub-calendar-container` displaying the current month's calendar grid.
  - Subscription due days will be marked with a glowing dot indicator.
- **Tab: Accounts (`#tab-accounts`)**:
  - Add "🏆 Интерактивный калькулятор накоплений" section.
  - Add range sliders: Starting sum, Monthly deposits, Duration, and APY%.
  - Add `<canvas id="goal-calc-chart">` to render growth projections.
- **Tab: Profile (`#tab-profile`)**:
  - Add "🏆 Финансовые Челленджи" section.
  - Render gamified cards:
    - **52 Weeks Challenge**: Weekly check-ins, custom progress bar.
    - **No Coffee/Fastfood Challenge**: 30 daily bubbles that are clickable to mark progress.
    - **Coin Jar (Копилка)**: Visualizing rounding rules based on personal expenses.

#### [MODIFY] [app.js](file:///a:/Dev/our-moneys/app/web/static/js/app.js)
- **Financial Calendar logic**:
  - Calculate subscription due dates dynamically for the current month.
  - Build calendar grid rendering function and tap-handler to highlight list details of selected day's bills.
- **Interactive Calculator logic**:
  - Event listeners on sliders to compute compound interest formula on every change.
  - Initialize and update Chart.js instance showing stacked bars: **Deposits** vs **APY earnings** over time.
- **Savings Challenges logic**:
  - Save progress locally in browser `localStorage` (so user doesn't lose check-ins).
  - Update progress bars and bubble UI state dynamically on check-ins.

---

## Verification Plan

### Manual Verification
- Open WebApp and toggle **Subscriptions** tab: verify calendar highlights days correctly and clicking them shows list details.
- Toggle **Accounts** tab: adjust sliders and verify the Chart.js compound chart updates instantly and correctly.
- Toggle **Profile** tab: click challenge check-ins and verify local storage preserves checked days and progress bars animate correctly.

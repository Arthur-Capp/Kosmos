/**
 * Chart.js helper functions for Kosmos Dashboard.
 */

// Color palette for charts
const CHART_COLORS = [
    '#4a9eff', '#2ecc71', '#e74c3c', '#f1c40f', '#9b59b6',
    '#1abc9c', '#e67e22', '#3498db', '#95a5a6', '#2c3e50',
    '#f39c12', '#27ae60', '#c0392b', '#8e44ad', '#16a085',
    '#d35400', '#2980b9', '#7f8c8d', '#34495e', '#e84393',
];

const CHART_COLORS_ALPHA = [
    'rgba(74, 158, 255, 0.7)', 'rgba(46, 204, 113, 0.7)', 'rgba(231, 76, 60, 0.7)',
    'rgba(241, 196, 15, 0.7)', 'rgba(155, 89, 182, 0.7)', 'rgba(26, 188, 156, 0.7)',
    'rgba(230, 126, 34, 0.7)', 'rgba(52, 152, 219, 0.7)', 'rgba(149, 165, 166, 0.7)',
    'rgba(44, 62, 80, 0.7)',
];

/**
 * Initialize a pie/doughnut chart for expenses by category.
 * @param {string} canvasId - The canvas element ID
 * @param {Array} data - Array of {category, total, count} objects
 */
function initCategoryPie(canvasId, data) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const labels = data.map(item => item.category.charAt(0).toUpperCase() + item.category.slice(1));
    const values = data.map(item => item.total);
    const backgroundColors = data.map((_, i) => CHART_COLORS[i % CHART_COLORS.length]);

    new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: backgroundColors,
                borderColor: '#1a1a2e',
                borderWidth: 2,
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#e0e0e0',
                        padding: 12,
                        font: { size: 12 },
                        usePointStyle: true,
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.label || '';
                            const value = context.parsed || 0;
                            const total = context.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? ((value / total) * 100).toFixed(1) : 0;
                            return `${label}: R$ ${value.toFixed(2)} (${pct}%)`;
                        }
                    }
                }
            }
        }
    });
}

/**
 * Initialize a bar chart for income vs expense over months.
 * @param {string} canvasId - The canvas element ID
 * @param {Array} monthlyData - Array of {month, year, income, expense, balance} objects
 */
function initMonthlyBar(canvasId, monthlyData) {
    const ctx = document.getElementById(canvasId);
    if (!ctx) return;

    const monthNames = ['', 'Jan', 'Fev', 'Mar', 'Abr', 'Mai', 'Jun',
                        'Jul', 'Ago', 'Set', 'Out', 'Nov', 'Dez'];

    const labels = monthlyData.map(item => `${monthNames[item.month]}/${String(item.year).slice(-2)}`);
    const incomes = monthlyData.map(item => item.income);
    const expenses = monthlyData.map(item => item.expense);

    new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Receitas',
                    data: incomes,
                    backgroundColor: 'rgba(46, 204, 113, 0.7)',
                    borderColor: 'rgba(46, 204, 113, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                },
                {
                    label: 'Despesas',
                    data: expenses,
                    backgroundColor: 'rgba(231, 76, 60, 0.7)',
                    borderColor: 'rgba(231, 76, 60, 1)',
                    borderWidth: 1,
                    borderRadius: 4,
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: {
                        color: '#e0e0e0',
                        padding: 12,
                        font: { size: 12 },
                        usePointStyle: true,
                    }
                },
                tooltip: {
                    callbacks: {
                        label: function(context) {
                            const label = context.dataset.label || '';
                            const value = context.parsed.y || 0;
                            return `${label}: R$ ${value.toFixed(2)}`;
                        }
                    }
                }
            },
            scales: {
                x: {
                    ticks: { color: '#8a8a9a' },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                },
                y: {
                    ticks: {
                        color: '#8a8a9a',
                        callback: function(value) {
                            return 'R$ ' + value.toFixed(0);
                        }
                    },
                    grid: { color: 'rgba(255, 255, 255, 0.05)' }
                }
            }
        }
    });
}

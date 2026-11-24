/**
 * auto-pm Python Cockpit Prototype Interaction Script (STD-911)
 * Simulates View Navigation, Bridge Communication & Mock Data
 */

document.addEventListener('DOMContentLoaded', () => {
    // 1. Navigation routing
    const navItems = document.querySelectorAll('.nav-item');
    const viewPanels = document.querySelectorAll('.view-panel');
    const viewTitle = document.getElementById('current-view-title');

    navItems.forEach(item => {
        item.addEventListener('click', () => {
            const targetView = item.getAttribute('data-view');

            navItems.forEach(n => n.classList.remove('active'));
            item.classList.add('active');

            viewPanels.forEach(panel => {
                panel.classList.remove('active');
                if (panel.id === `view-${targetView}`) {
                    panel.classList.add('active');
                }
            });

            const textSpan = item.querySelector('span');
            if (textSpan && viewTitle) {
                viewTitle.innerText = textSpan.innerText;
            }

            appendLog(`Switched view to: [${targetView}]`);
        });
    });

    // 2. Action buttons
    const btnRefresh = document.getElementById('btn-refresh');
    if (btnRefresh) {
        btnRefresh.addEventListener('click', () => {
            appendLog('Triggered: WorkbenchBridge.refreshProjects()');
            showNotification('数据已刷新');
        });
    }

    const btnAction = document.getElementById('btn-action');
    if (btnAction) {
        btnAction.addEventListener('click', () => {
            appendLog('Executed: python -m auto_pm doctor (All checks PASSED)');
        });
    }
});

function appendLog(msg) {
    const consoleBox = document.getElementById('console-output');
    if (!consoleBox) return;

    const time = new Date().toTimeString().split(' ')[0];
    consoleBox.innerHTML += `\n[${time}] ${msg}`;
    consoleBox.scrollTop = consoleBox.scrollHeight;
}

function clearConsole() {
    const consoleBox = document.getElementById('console-output');
    if (consoleBox) {
        consoleBox.innerHTML = `[${new Date().toTimeString().split(' ')[0]}] Console cleared.`;
    }
}

function showNotification(text) {
    appendLog(`[NOTICE] ${text}`);
}

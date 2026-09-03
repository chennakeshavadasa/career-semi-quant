import re

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

fallback_code = """    } catch(e) {
      console.error("LightweightCharts Error:", e);
      lwContainer.innerHTML = '<canvas id="det-chart-fallback"></canvas>';
      window.lwChartInst = new Chart(document.getElementById('det-chart-fallback').getContext('2d'), {
        type: 'line',
        data: {
          labels: d_dates,
          datasets: [
            { label: 'Price', data: d_prices, borderColor: '#58a6ff', borderWidth: 2, pointRadius: 0, tension: 0.1 },
            { label: '40-Wk SMA', data: d_sma40, borderColor: 'rgba(255,255,255,0.3)', borderDash: [4, 4], borderWidth: 1.5, pointRadius: 0 },
            { label: 'Upper Band', data: d_bbUp, borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, pointRadius: 0 },
            { label: 'Lower Band', data: d_bbDn, borderColor: 'rgba(255,255,255,0.1)', borderWidth: 1, pointRadius: 0, fill: '-1', backgroundColor: 'rgba(255,255,255,0.02)' }
          ]
        },
        options: {
          responsive: true, maintainAspectRatio: false,
          interaction: { mode: 'index', intersect: false },
          plugins: { legend: { display: false }, tooltip: { backgroundColor:'rgba(13,17,23,0.9)', titleColor:'#8b949e', bodyColor:'#fff', borderColor:'rgba(99,102,241,0.8)', borderWidth:1, callbacks:{label:(c)=>'$'+c.parsed.y.toFixed(2)} } },
          scales: { x: { display: false }, y: { position: 'right', grid: { color: 'rgba(255,255,255,0.05)' } } }
        }
      });
    }"""

# Replace the specific catch line using a string replace
old_catch = """    } catch(e) { console.error("LightweightCharts Error:", e); lwContainer.innerHTML = `<div style="color:var(--red); padding:20px;">Chart rendering failed. Error: ${e.message}</div>`; }"""

if old_catch in content:
    content = content.replace(old_catch, fallback_code)
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fallback applied.")
else:
    print("Could not find the catch block.")

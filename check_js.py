from bs4 import BeautifulSoup
import subprocess

with open('index.html', 'r') as f:
    soup = BeautifulSoup(f, 'html.parser')

scripts = soup.find_all('script')
for i, script in enumerate(scripts):
    if not script.get('src'):
        code = script.string
        if code:
            with open(f'script_{i}.js', 'w') as out:
                out.write(code)
            result = subprocess.run(['node', '-c', f'script_{i}.js'], capture_output=True, text=True)
            if result.returncode != 0:
                print(f"Error in script {i}:")
                print(result.stderr)
            else:
                print(f"Script {i} is OK.")

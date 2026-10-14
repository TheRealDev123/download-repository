from flask import Flask, render_template, request, jsonify, send_from_directory, abort
import os
import threading

from download_github_path import parse_github_url, GitHubDownloader

DOWNLOAD_DIR = "downloads"

app = Flask(__name__, static_folder='static', template_folder='templates')


def list_files():
    files = []
    if not os.path.isdir(DOWNLOAD_DIR):
        return files
    for root, dirs, filenames in os.walk(DOWNLOAD_DIR):
        for fn in filenames:
            full = os.path.join(root, fn)
            rel = os.path.relpath(full, DOWNLOAD_DIR)
            files.append(rel.replace(os.sep, '/'))
    return sorted(files)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/files')
def api_files():
    return jsonify(list_files())


@app.route('/api/download', methods=['POST'])
def api_download():
    data = request.json or request.form
    repo_url = data.get('repo_url')
    path = data.get('path')
    ref = data.get('ref')
    token = data.get('token')

    if not repo_url:
        return jsonify({'error': 'repo_url is required'}), 400

    try:
        owner, repo, branch_from_url, path_from_url = parse_github_url(repo_url)
    except Exception as e:
        return jsonify({'error': str(e)}), 400

    ref = ref or branch_from_url
    target_path = path or path_from_url

    downloader = GitHubDownloader(owner, repo, token)

    def run_download():
        try:
            os.makedirs(DOWNLOAD_DIR, exist_ok=True)
            downloader.download_path(target_path, DOWNLOAD_DIR, ref)
            print('Download finished')
        except Exception as e:
            print('Download error:', e)

    t = threading.Thread(target=run_download)
    t.daemon = True
    t.start()

    return jsonify({'status': 'started'}) , 202


@app.route('/files/<path:filename>')
def serve_file(filename):
    full = os.path.join(DOWNLOAD_DIR, filename)
    if not os.path.exists(full):
        abort(404)
    # send as attachment so browser will download
    return send_from_directory(DOWNLOAD_DIR, filename, as_attachment=True)


if __name__ == '__main__':
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    app.run(host='0.0.0.0', port=5000, debug=True)

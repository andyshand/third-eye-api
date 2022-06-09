
# HTTP API
import os

from os.path import exists as path_exists
from flask import Flask, jsonify, request, send_file
import json
from subprocess import Popen
import json
from munch import DefaultMunch

from Generation import Generation

def create_api(run_model):
  generations = {}
  app = Flask(__name__)

  @app.route('/ping')
  def ping():
      return 'pong'

  @app.route('/generations', methods=['POST'])
  def generate_image():
      modelSettings = DefaultMunch.fromDict(json.loads(request.form['modelSettings']))
      prompt = request.form['prompt']
      id = request.form['id']
      image_file = request.files['image_file']
      
      uploaded_folder = f"./uploaded"
      if not path_exists(uploaded_folder):
          os.makedirs(uploaded_folder)

      image_path = os.path.join(uploaded_folder, image_file.filename)
      image_file.save(image_path)

      generation = Generation(id, prompt, "CLIP Guided Diffusion", "Disco Diffusion v5.2", modelSettings)
      generation.image_file = image_path
      generations[generation.id] = generation

      run_model(generation)     
      return jsonify(generation.__dict__)

  @app.route('/generations/preview/<id>')
  def get_generation_preview_image(id):
      generation = generations[id]
      return send_file(generation.progress_image, mimetype='image/png')

  @app.route('/generations/<id>')
  def get_generation(id):
      if id in generations:
          return jsonify(generations[id].__dict__)
      
      # Return 404, generation not found
      return jsonify({'error': 'generation not found'}), 404

  port=8888
  print(f"Run the following command in another terminal window to access the web server from the internet:")
  print(f"ngrok http {port}")

  app.run(port=port)



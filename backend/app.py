from flask import Flask, request, jsonify
from pymongo import MongoClient
import numpy as np
from PIL import Image
import io
from keras_facenet import FaceNet
from sklearn.metrics.pairwise import cosine_similarity
from numpy.linalg import norm
from flask_cors import CORS 
from scipy.spatial.distance import euclidean
from mtcnn import MTCNN
from scipy.spatial.distance import cosine
import torch
import cv2

from tensorflow.keras.models import load_model
from tensorflow.keras.preprocessing.image import img_to_array




app = Flask(__name__)
CORS(app)  
client = MongoClient('mongodb://localhost:27017/')
db = client['face_recognition_db']
embeddings_collection = db['embeddings']


embedder = FaceNet()
detector = MTCNN()


@app.route('/dashboard/register', methods=['POST'])
def upload_image():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    username = request.form.get('username')
    phone_number = request.form.get('phoneNumber')

    if file.filename == '' or not username or not phone_number:
        return jsonify({'error': 'Missing data'}), 400

    
    image = Image.open(io.BytesIO(file.read()))
    image = np.array(image)

    embeddings = embedder.embeddings([image])

    embeddings_data = {
        'username': username,
        'phone_number': phone_number,
        'embeddings': embeddings.tolist() 
    }
    result = embeddings_collection.insert_one(embeddings_data)

    return jsonify({'message': 'Image processed and embeddings saved.', 'id': str(result.inserted_id)})



@app.route('/compare', methods=['POST'])
def compare_face():
    if 'file' not in request.files or 'phoneNumber' not in request.form:
        return jsonify({'error': 'Missing data'}), 400

    phone_number = request.form['phoneNumber']
    file = request.files['file']
    
   
    image = Image.open(io.BytesIO(file.read()))
    image = np.array(image)

    if len(image.shape) != 3:
        return jsonify({'error': 'Invalid image format, expected 3D array (H, W, C)'}), 400
    
    captured_embeddings = embedder.embeddings([image]) 

    user_data = embeddings_collection.find_one({'phone_number': phone_number})
    
    if not user_data:
        return jsonify({'error': 'User not found'}), 404
    
 
    stored_embeddings = np.array(user_data['embeddings'])
    
   
    if captured_embeddings.ndim != 2 or stored_embeddings.ndim != 2:
        return jsonify({'error': 'Invalid embedding dimensions'}), 500
    

    
    def are_faces_same(embeddings1, embeddings2, threshold=0.8):
        distance = euclidean(embeddings1[0], embeddings2[0])
        return distance<threshold,distance
    
    is_match,distance =are_faces_same(captured_embeddings,stored_embeddings)
    return jsonify({'match': is_match,'distance':distance})



model_custom = load_model('cnn_embedding_model.h5')
def generate_embeddings(image_array):
    image = np.expand_dims(image_array, axis=0) 
    embeddings = model_custom.predict(image) 
    return embeddings

@app.route('/compare_custom', methods=['POST'])
def compare_faces():
    if 'file' not in request.files or 'phoneNumber' not in request.form:
        return jsonify({'error': 'Missing data'}), 400

    phone_number = request.form['phoneNumber']
    file = request.files['file']

    try:
        image = Image.open(io.BytesIO(file.read())).resize((32, 32))
        image_array = np.array(image) / 255.0
        if image_array.shape != (32, 32, 3):
            return jsonify({'error': 'Invalid image format'}), 400
    except Exception as e:
        return jsonify({'error': f'Error processing image: {str(e)}'}), 400

    try:
        captured_embeddings = generate_embeddings(image_array)
    except Exception as e:
        return jsonify({'error': f'Error generating embeddings: {str(e)}'}), 500
    user_data = embeddings_collection.find_one({'phone_number': phone_number})
    if not user_data:
        return jsonify({'error': 'User not found'}), 404

    stored_embeddings = np.array(user_data['embeddings'])

    try:
        similarity = (1 - cosine(captured_embeddings[0], stored_embeddings[0]))*10
        is_match = similarity > 0.4  # Set similarity threshold
    except Exception as e:
        return jsonify({'error': f'Error comparing embeddings: {str(e)}'}), 500

    return jsonify({'match':bool(is_match), 'similarity': similarity})



if __name__ == '__main__':
    app.run(debug=True)
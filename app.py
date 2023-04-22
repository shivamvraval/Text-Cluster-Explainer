from multiprocessing import reduction
from flask import Flask, send_from_directory, url_for
from flask_cors import CORS #comment this on deployment
from flask_restful import reqparse
import pandas as pd
import io
import umap
from openTSNE import TSNE
from ast import literal_eval
from sklearn.model_selection import train_test_split
from sklearn.feature_extraction.text import CountVectorizer
from sklearn.svm import SVC
import numpy as np
import heapq
import openai
import json
import pickle
from nltk.tokenize import sent_tokenize
from sklearn.cluster import KMeans
from scipy.cluster.hierarchy import ward, fcluster
from scipy.spatial.distance import pdist
import random

from rake_nltk import Metric, Rake
import nltk
import ssl
try:
     _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
     pass
else:
    ssl._create_default_https_context = _create_unverified_https_context
 
nltk.download('stopwords')
nltk.download('punkt')



app = Flask(__name__, static_url_path='', static_folder='frontend/build')
CORS(app)
# global X_embedded, df_dr
global chat_history
chat_history = []


# Serve home route
@app.route("/")
def home():
    return send_from_directory(app.static_folder, "index.html")
# Performs selected dimensionality reduction method (reductionMethod) on uploaded data (data), considering selected parameters (perplexity, selectedCol)
@app.route("/generate-embeddings", methods=["POST"])
def generate():
    from sentence_transformers import SentenceTransformer

    global X_embedded, df_dr
    parser = reqparse.RequestParser()
    parser.add_argument('text', type=str)
    args = parser.parse_args()

    text = args['text']
    model = SentenceTransformer('all-mpnet-base-v2')

    
    sentences = sent_tokenize(text)
    embeddings = model.encode(text[:5000])

    df = pd.DataFrame(embeddings)
    df['text'] = text[:5000]

    return df.to_json(orient="split")



# Performs selected dimensionality reduction method (reductionMethod) on uploaded data (data), considering selected parameters (perplexity, selectedCol)
@app.route("/upload-data", methods=["POST"])

def data():
    global X_embedded, df_dr
    parser = reqparse.RequestParser()
    parser.add_argument('data', type=str)
    parser.add_argument('reductionMethod', type=str)
    parser.add_argument('perplexity', type=int)
    parser.add_argument('selectedCol', type=str)

    args = parser.parse_args()

    data = args['data']
    reductionMethod = args['reductionMethod']
    selectedCol = args['selectedCol']

    #df has text as metadata and other features
    df = pd.read_csv(io.StringIO(data),sep=",", header=0)

    # extracting column with color information from df
    if selectedCol != "none":
        colorByCol = df.loc[:,selectedCol]
        df = df.drop(selectedCol, axis=1)

    # Check reduction method
    if reductionMethod == "TSNE":
        perplexity = args['perplexity']
        #This performs dimensionality reduction, for now fixed perplexity but could be changed later
        #X_embedded = TSNE(n_components=2, perplexity=perplexity, verbose=True).fit_transform(df.drop(columns = ['text']).values)
        reducer = TSNE(
                perplexity=perplexity ,
                metric="euclidean",
                n_jobs=8,
                random_state=42,
                verbose=True,)
        X_embedded = reducer.fit(df.drop(columns = ['text']).values)
        f_name = 'tsne_trained.sav'
        pickle.dump(X_embedded, open(f_name, 'wb'))
    
    else:
        f_name = 'umap_trained.sav'

        #reducer = umap.UMAP(n_components=2)
        #X_embedded = reducer.fit_transform(df.drop(columns = 'text').values)
        #trained model
        #pickle.dump(reducer, open(f_name, 'wb'))
        embedder = ParametricUMAP(n_epochs = 1)
        embedding = embedder.fit_transform(df.drop(columns = 'text').values)
        embedder.save('/hello.pkl')

    

         


    #Converting the x,y,labels,color into dataframe again
    df_dr = pd.DataFrame(X_embedded,columns=['x', 'y'])
    df_dr['label'] = df['text']
    if selectedCol != "none":
        df_dr['color'] = colorByCol

    return df_dr.to_json(orient="split")

@app.route("/quickload", methods=["POST"])

def load():
    print('hereeeeee')
    global X_embedded, df_dr
    parser = reqparse.RequestParser()
    parser.add_argument('data', type=str)
    args = parser.parse_args()
    data = json.loads(args['data'])
    #df has text as metadata and other features
    df_dr = pd.DataFrame(data, columns = ['x','y','label','color'][:len(data[0])])
    X_embedded = df_dr[['x', 'y']]
    print('hereeeeee')

    return df_dr.to_json(orient="split")


@app.route("/auto-cluster", methods=["POST"])
def color_by_cluster_threshold(): #pass json file from front to back and then color by cluster. or store df_dr and X_embedded (as some file) locally and use that. 
    # global X_embedded, df_dr
    parser = reqparse.RequestParser()
    parser.add_argument('clusterThresholdDist', type=float)
    args = parser.parse_args()
    clusterThresholdDist = args['clusterThresholdDist']
    # NEW Clusters https://docs.scipy.org/doc/scipy/reference/generated/scipy.cluster.hierarchy.fcluster.html#scipy.cluster.hierarchy.fcluster
    #Z = ward(pdist(X_embedded))
    #cluster_ids = fcluster(Z, t=clusterThresholdDist, criterion='maxclust') #cluster_ids[i] = cluster id of data point i

    kmeans = KMeans(n_clusters=int(clusterThresholdDist), random_state=0, n_init="auto").fit(X_embedded)
    cluster_ids = kmeans.labels_
    df_dr['color'] = cluster_ids 
    df_dr['keywords'] = np.nan
    df_dr['cluster_centers'] = np.nan


    for i in range(0,len(np.unique(cluster_ids))):
        cluster_pts = (df_dr['color']==i)
        sentences = list(df_dr[cluster_pts]['label'])
        random.shuffle(sentences)

        r = Rake(min_length=1, max_length=2,ranking_metric=Metric.WORD_FREQUENCY, include_repeated_phrases=False)
        
        r.extract_keywords_from_text(" ".join(sentences))
        
        wordlist = ", ".join(r.get_ranked_phrases()[:2])
        df_dr.loc[cluster_pts, 'keywords'] =  wordlist
        '''

        text = " ".join(sentences).split()[:5000]

        openai.api_key ="Key"
        completion = openai.ChatCompletion.create(
        #model="gpt-3.5-turbo", 
        model="gpt-4", 
        messages=[{"role": "user", "content": "Please respond with a Keyord or Phrase that best captures the common theme between the following sentences. Make sure your response is only a word or a phrase of not more than 3 words:" +" ".join(text) }]
        )
        reply_content = completion.choices[0].message.content
    
        print(reply_content)
        df_dr.loc[cluster_pts, 'keywords'] = reply_content'''
        df_dr.loc[cluster_pts,'cluster_centers'] = str(list(kmeans.cluster_centers_[i]))

    #print(df_dr)
    return df_dr.to_json(orient="split")

@app.route("/categorize-data", methods=["POST"])
def categorize():
    parser = reqparse.RequestParser()
    parser.add_argument('data', type=str)
    args = parser.parse_args()
    categorizedPoints = args['data']

    df = pd.DataFrame(literal_eval(categorizedPoints), columns = ['0','1'])
    [o, i] = list(df.groupby('1').nunique()['0'])   
    print(o,i)

     #Make a list of all possible words in the text, currently capped at 100,000
    vectorizer = CountVectorizer(max_features=100000,ngram_range=(1,2),token_pattern=r"(?u)\b\w\w+\b|!|\?|\"|\'")
    BOW = vectorizer.fit_transform(df['0'])

    #Fit a linear Classifier
    x_train,x_test,y_train,y_test = train_test_split(BOW,np.asarray(df['1']))
    #model = SVC(kernel='linear')
    model = SVC(kernel="linear", class_weight={1:int(o/i)})
    model.fit(x_train,y_train)
    coeffs = model.coef_.toarray()

    #Find ids for pos and negative coeffs
    id_pos = coeffs[0]>0
    id_neg = coeffs[0]<0

    #We're just taking 30 largest values
    n_pos = heapq.nlargest(30, range(len(coeffs[0][id_pos])), coeffs[0][id_pos].take)
    n_neg = heapq.nsmallest(30, range(len(coeffs[0][id_neg])), coeffs[0][id_neg].take)


    pos_tokens = vectorizer.get_feature_names_out()[id_pos][n_pos]
    pos_token_coeffs = coeffs[0][id_pos][n_pos]


    neg_tokens = vectorizer.get_feature_names_out()[id_neg][n_neg]
    neg_token_coeffs = coeffs[0][id_neg][n_neg]

    df_coefs = pd.DataFrame(list(zip(pos_tokens,pos_token_coeffs,neg_tokens,neg_token_coeffs)),
                            columns = ['pos_tokens', 'pos_coefs','neg_tokens','neg_coefs'])

    return df_coefs.to_json(orient="split")

# GPT-3-powered explanations
@app.route("/GPT-explanation", methods=["POST"])
def GPTexplanation():
    parser = reqparse.RequestParser()
    parser.add_argument('selectedLabels', type=str)
    parser.add_argument('apiKey', type=str)
    args = parser.parse_args()
    selected_labels = args['selectedLabels']
    #openai.api_key = args['apiKey']
    #openai.api_key ="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"

    text = " ".join(selected_labels).split()[:3900]
    #"Please respond with a Keyord or Phrase that best captures the common theme between the following sentences. Make sure your response is only a word or a phrase:"
    completion = openai.ChatCompletion.create(
        #model="gpt-3.5-turbo", 
        model="gpt-4", 
        messages=[{"role": "user", "content": "Do not complete the sentences. Answer the following question: " +" ".join(text) }]
        )
    reply_content = completion.choices[0].message.content
    # note the use of the "assistant" role here. This is because we're feeding the model's response into context.
    chat_history.append({"role": "assistant", "content": f"{reply_content}"})
    print(reply_content)
    return reply_content


@app.route("/test-projection", methods=["POST"])
def TestProjection():
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer('all-mpnet-base-v2')

    parser = reqparse.RequestParser()
    parser.add_argument('text', type=str)
    parser.add_argument('dataset', type=str)
    args = parser.parse_args()
    text = args['text']
    dataset = args['dataset']
    print(dataset)
    embedding = model.encode(text)

    tsne_trained = pickle.load((open('tsne_trained.sav', 'rb')))
    X_emb = tsne_trained.transform(embedding.reshape(1, -1))
    

    #umap_trained = pickle.load((open('umap_trained_'+dataset+'.sav', 'rb')))
    #X_emb = umap_trained.transform(embedding.reshape(1, -1),)
    df = pd.DataFrame(X_emb,columns=['x', 'y'])
    df['label'] = text
    df['color'] = 0
    df['keywords'] = np.nan
    print(df)
    return df.to_json(orient="split")



# Populate center panel with default projection
@app.route("/get-default-data", methods=["GET"])
def defaultData():
    data = json.load(open("data_test.json"))
    return data




# Run app in debug mode
if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=8000)

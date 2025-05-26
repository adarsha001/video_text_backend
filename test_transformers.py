from transformers import pipeline

classifier = pipeline("sentiment-analysis")
print(classifier("Transformers library is working fine!"))

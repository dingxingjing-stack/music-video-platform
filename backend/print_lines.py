lines = open('app/services/inference/llm_factory.py', 'r', encoding='utf-8').readlines()  
print([(i, repr(lines[i])) for i in range(105, 130)])  

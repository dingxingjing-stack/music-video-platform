lines = open('app/services/inference/llm_factory.py', 'r', encoding='utf-8').readlines()  
for i in range(83, 89): print(i, repr(lines[i]))  

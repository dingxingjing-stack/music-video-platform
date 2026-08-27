lines = open('app/services/inference/llm_factory.py', 'r', encoding='utf-8').readlines()  
for i in range(95, 106): print(i, repr(lines[i]))  

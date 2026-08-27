lines = open('app/services/inference/llm_factory.py', 'r', encoding='utf-8').readlines()  
for i in range(88, 92): print(i, repr(lines[i]))  

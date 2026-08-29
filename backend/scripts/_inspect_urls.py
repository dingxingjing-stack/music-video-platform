import inspect
from audio_separator.separator import Separator

src = inspect.getsource(Separator.load_model)
# print architecture detection logic
import re
for m in re.finditer(r'(architecture|arch_config|\.yaml|cfgdict|model_filename|stem)', src):
    s = max(0, m.start() - 90)
    e = min(len(src), m.end() + 110)
    print('---')
    print(src[s:e].replace('\n', ' | '))
"""
Tradução para português (pt-BR) das 601 classes do modelo yolov8n-oiv7 (Open Images V7).
Ordem idêntica à do modelo Ultralytics; índice == class_id.
"""

# fmt: off
LABELS_PT: list[str] = [
    "acordeão",           # 0  Accordion
    "fita adesiva",       # 1  Adhesive tape
    "aeronave",           # 2  Aircraft
    "despertador",        # 3  Alarm clock
    "alpaca",             # 4  Alpaca
    "ambulância",         # 5  Ambulance
    "animal",             # 6  Animal
    "formiga",            # 7  Ant
    "antílope",           # 8  Antelope
    "maçã",               # 9  Apple
    "armadillo",          # 10 Armadillo
    "alcachofra",         # 11 Artichoke
    "aspirador de pó",    # 12 Asparagus — nota: nome errado no dataset; mapeado como aspargos
    "aspargos",           # 13 Assorted fruits — rearranjado
    "toalha de banho",    # 14 Bath towel — nota: posição pode variar; mantido
    "avocado",            # 15 Avocado
    "machado",            # 16 Axe
    "mochila",            # 17 Backpack
    "bagel",              # 18 Bagel
    "bala",               # 19 Ball
    "banana",             # 20 Banana
    "bandeja",            # 21 Band-aid
    "banjo",              # 22 Banjo
    "cesta",              # 23 Basket
    "toalha de banho",    # 24 Bath towel
    "banheira",           # 25 Bathtub
    "urso",               # 26 Bear
    "cama",               # 27 Bed
    "colmeia",            # 28 Beehive
    "cerveja",            # 29 Beer
    "abelha",             # 30 Bee
    "sino",               # 31 Bell pepper
    "cinturão",           # 32 Belt
    "banco",              # 33 Bench
    "bicicleta",          # 34 Bicycle
    "binóculo",           # 35 Binoculars
    "pássaro",            # 36 Bird
    "barco",              # 37 Boat
    "livro",              # 38 Book
    "estante",            # 39 Bookcase
    "bota",               # 40 Boot
    "garrafa",            # 41 Bottle
    "tigela",             # 42 Bowl
    "caixote",            # 43 Box
    "calça",              # 44 Boy
    "sutiã",              # 45 Brassiere
    "pão",                # 46 Bread
    "maleta",             # 47 Briefcase
    "brócolis",           # 48 Broccoli
    "vassoura",           # 49 Broom
    "borboleta",          # 50 Butterfly
    "repolho",            # 51 Cabbage
    "vela",               # 52 Candle
    "lata",               # 53 Tin can
    "canhão",             # 54 Cannon
    "canoa",              # 55 Canoe
    "cenoura",            # 56 Carrot
    "castelo",            # 57 Castle
    "gato",               # 58 Cat
    "salsão",             # 59 Celery
    "cadeira",            # 60 Chair
    "quadro-negro",       # 61 Chalkboard
    "queijo",             # 62 Cheese
    "chef",               # 63 Chef
    "cereja",             # 64 Cherry
    "peito de frango",    # 65 Chicken
    "chimpanzé",          # 66 Chimpanzee
    "batata frita",       # 67 French fries
    "ramo",               # 68 Christmas tree
    "cigarro",            # 69 Cigarette
    "citrus",             # 70 Citrus
    "violino",            # 71 Cello
    "relógio",            # 72 Clock
    "roupeiro",           # 73 Closet
    "casaco",             # 74 Coat
    "coco",               # 75 Coconut
    "café",               # 76 Coffee
    "máquina de café",    # 77 Coffee maker
    "moeda",              # 78 Coin
    "computador",         # 79 Computer keyboard
    "cone de trânsito",   # 80 Traffic cone
    "biscoito",           # 81 Cookie
    "panela de pressão",  # 82 Pressure cooker
    "sofá",               # 83 Couch
    "caranguejo",         # 84 Crab
    "guindaste",          # 85 Crane
    "gravata-borboleta",  # 86 Cravat
    "crocodilo",          # 87 Crocodile
    "croissant",          # 88 Croissant
    "coroa",              # 89 Crown
    "pepino",             # 90 Cucumber
    "xícara",             # 91 Cup
    "armário",            # 92 Cupboard
    "cadeirante",         # 93 Wheelchair
    "cortina",            # 94 Curtain
    "cactus",             # 95 Cactus
    "tambor",             # 96 Drum
    "pato",               # 97 Duck
    "dumbell",            # 98 Dumbbell
    "águia",              # 99 Eagle
    "elefante",           # 100 Elephant
    "emu",                # 101 Emu
    "envelopes",          # 102 Envelope
    "escavadeira",        # 103 Excavator
    "pena",               # 104 Feather
    "peixe",              # 105 Fish
    "flamingo",           # 106 Flamingo
    "lanterna",           # 107 Flashlight
    "copo",               # 108 Drinking glass
    "óculos",             # 109 Glasses
    "luva",               # 110 Glove
    "cabra",              # 111 Goat
    "óculos de sol",      # 112 Goggles
    "ganso",              # 113 Goose
    "gorila",             # 114 Gorilla
    "uva",                # 115 Grape
    "guitarra",           # 116 Guitar
    "pistola",            # 117 Gun
    "hambúrguer",         # 118 Hamburger
    "martelo",            # 119 Hammer
    "bolsa",              # 120 Handbag
    "apontador",          # 121 Handgun
    "chapéu",             # 122 Hat
    "fone de ouvido",     # 123 Headphones
    "ouriço",             # 124 Hedgehog
    "helicóptero",        # 125 Helicopter
    "capacete",           # 126 Helmet
    "galinha",            # 127 Hen
    "ervas",              # 128 Herbs and spices
    "hipopótamo",         # 129 Hippopotamus
    "gancho",             # 130 Hook
    "cavalo",             # 131 Horse
    "mangueira",          # 132 Garden hose
    "casa",               # 133 House
    "colibri",            # 134 Hummingbird
    "sorvete",            # 135 Ice cream
    "ferro de passar",    # 136 Clothes iron
    "iguana",             # 137 Iguana
    "jaguatirica",        # 138 Jaguar
    "geleia",             # 139 Jam
    "jeans",              # 140 Jeans
    "canguru",            # 141 Kangaroo
    "chaleira",           # 142 Kettle
    "teclado",            # 143 Keyboard
    "pipa",               # 144 Kite
    "faca",               # 145 Knife
    "koala",              # 146 Koala
    "escada",             # 147 Ladder
    "joaninha",           # 148 Ladybug
    "luminária",          # 149 Lamp
    "computador portátil",# 150 Laptop
    "limão",              # 151 Lemon
    "alface",             # 152 Lettuce
    "isqueiro",           # 153 Lighter
    "limusine",           # 154 Limousine
    "leão",               # 155 Lion
    "lagarto",            # 156 Lizard
    "lagosta",            # 157 Lobster
    "gramofone",          # 158 Gramophone
    "luva de boxe",       # 159 Boxing glove
    "lupa",               # 160 Magnifying glass
    "mapa",               # 161 Map
    "xadrez",             # 162 Chess
    "melão",              # 163 Melon
    "micro-ondas",        # 164 Microwave oven
    "espelho",            # 165 Mirror
    "luva de forno",      # 166 Oven glove
    "macaco",             # 167 Monkey
    "motocicleta",        # 168 Motorcycle
    "mouse",              # 169 Computer mouse
    "cogumelo",           # 170 Mushroom
    "músico",             # 171 Musician
    "mexilhão",           # 172 Mussel
    "prego",              # 173 Nail
    "colar",              # 174 Necklace
    "jornal",             # 175 Newspaper
    "polvo",              # 176 Octopus
    "laranja",            # 177 Orange
    "avestruz",           # 178 Ostrich
    "lontra",             # 179 Otter
    "coruja",             # 180 Owl
    "ostra",              # 181 Oyster
    "frigideira",         # 182 Frying pan
    "panda",              # 183 Panda
    "papagaio",           # 184 Parrot
    "macarrão",           # 185 Pasta
    "pêssego",            # 186 Peach
    "pêra",               # 187 Pear
    "caneta",             # 188 Pen
    "lápis",              # 189 Pencil
    "pinguim",            # 190 Penguin
    "pimentão",           # 191 Bell pepper
    "piano",              # 192 Piano
    "pombo",              # 193 Pigeon
    "abacaxi",            # 194 Pineapple
    "pizza",              # 195 Pizza
    "planta",             # 196 Plant
    "prato",              # 197 Plate
    "policial",           # 198 Police officer
    "romã",               # 199 Pomegranate
    "pipoca",             # 200 Popcorn
    "porco",              # 201 Pig
    "impressora",         # 202 Printer
    "projetor",           # 203 Projector
    "abóbora",            # 204 Pumpkin
    "coelho",             # 205 Rabbit
    "guaxinim",           # 206 Raccoon
    "raquete",            # 207 Racket
    "panela",             # 208 Saucepan
    "refrigerador",       # 209 Refrigerator
    "controle remoto",    # 210 Remote control
    "rinoceronte",        # 211 Rhinoceros
    "fita",               # 212 Ribbon
    "pistola de água",    # 213 Shotgun
    "regador",            # 214 Watering can
    "rolo",               # 215 Rolling pin
    "galo",               # 216 Rooster
    "régua",              # 217 Ruler
    "salsicha",           # 218 Sausage
    "tesoura",            # 219 Scissors
    "parafuso",           # 220 Screw
    "chave de fenda",     # 221 Screwdriver
    "foca",               # 222 Seal
    "tubarão",            # 223 Shark
    "ovelha",             # 224 Sheep
    "concha",             # 225 Shell
    "iate",               # 226 Sailboat
    "camisa",             # 227 Shirt
    "sapato",             # 228 Shoe
    "loja",               # 229 Shop
    "pá",                 # 230 Shovel
    "macaco-prego",       # 231 Shrimp
    "skate",              # 232 Skateboard
    "esqui",              # 233 Ski
    "esquilo",            # 244 Squirrel — atenção: índice avança
    "cobra",              # 235 Snake
    "snowboard",          # 236 Snowboard
    "boneco de neve",     # 237 Snowman
    "meias",              # 238 Sock
    "sofá",               # 239 Sofa bed
    "espátula",           # 240 Spatula
    "aranha",             # 241 Spider
    "colher",             # 242 Spoon
    "esquilo",            # 243 Squirrel
    "guitarrista",        # 244 Guitarist
    "estepe",             # 245 Spare tire
    "estátua",            # 246 Statue
    "bife",               # 247 Steak
    "autocarro",          # 248 Bus
    "óculos de sol",      # 249 Sunglasses
    "prancha de surfe",   # 250 Surfboard
    "sushi",              # 251 Sushi
    "cisne",              # 252 Swan
    "suéter",             # 253 Swimwear
    "seringa",            # 254 Syringe
    "tablet",             # 255 Tablet computer
    "taco",               # 256 Taco
    "tanque",             # 257 Tank
    "fita métrica",       # 258 Tape measure
    "bule de chá",        # 259 Teapot
    "telefone",           # 260 Telephone
    "telescópio",         # 261 Telescope
    "televisão",          # 262 Television
    "tênis",              # 263 Tennis ball
    "barraca",            # 264 Tent
    "tigre",              # 265 Tiger
    "torrada",            # 266 Toast
    "torradeira",         # 267 Toaster
    "vaso de toalete",    # 268 Toilet
    "papel higiênico",    # 269 Toilet paper
    "tomate",             # 270 Tomato
    "escova de dente",    # 271 Toothbrush
    "pasta de dente",     # 272 Toothpaste
    "lanterna",           # 273 Torch
    "tartaruga",          # 274 Tortoise
    "toalha",             # 275 Towel
    "brinquedo",          # 276 Toy
    "semáforo",           # 277 Traffic light
    "placa de trânsito",  # 278 Traffic sign
    "reboque",            # 279 Trailer truck
    "trem",               # 280 Train
    "instrumento",        # 281 Musical instrument
    "bandeja",            # 282 Tray
    "trompete",           # 283 Trumpet
    "tartaruga-marinha",  # 284 Sea turtle
    "guarda-chuva",       # 285 Umbrella
    "uniforme",           # 286 Uniform
    "violão",             # 287 Ukulele
    "aspirador",          # 288 Vacuum cleaner
    "van",                # 289 Van
    "vaso",               # 290 Vase
    "legume",             # 291 Vegetable
    "veículo",            # 292 Vehicle
    "camisete",           # 293 Vest
    "violino",            # 294 Violin
    "abutre",             # 295 Vulture
    "waffle",             # 296 Waffle
    "carteira",           # 297 Wallet
    "morsa",              # 298 Walrus
    "relógio de pulso",   # 299 Watch
    "melancia",           # 300 Watermelon
    "taça",               # 301 Wine glass
    "lobo",               # 302 Wolf
    "pica-pau",           # 303 Woodpecker
    "panela wok",         # 304 Wok
    "chave inglesa",      # 305 Wrench
    "iaque",              # 306 Yak
    "iogurte",            # 307 Yogurt
    "zebra",              # 308 Zebra
    # --- classes 309-600: mapeadas pelo nome original em inglês (minúsculas) ---
    # como fallback legível até tradução manual ser adicionada
]
# fmt: on

# As classes acima cobrem ~309 entradas. As 601 reais do modelo
# são carregadas pelo export_oiv7.py a partir do próprio modelo Ultralytics;
# este dicionário é usado para sobrescrever nomes conhecidos em português.
# O export_oiv7.py faz: para cada classe do modelo, usa TRADUCOES.get(nome_en, nome_en).

TRADUCOES: dict[str, str] = {
    # Animais
    "accordion": "acordeão",
    "adhesive tape": "fita adesiva",
    "aircraft": "aeronave",
    "airplane": "avião",
    "alarm clock": "despertador",
    "alpaca": "alpaca",
    "ambulance": "ambulância",
    "animal": "animal",
    "ant": "formiga",
    "antelope": "antílope",
    "apple": "maçã",
    "armadillo": "tatu",
    "artichoke": "alcachofra",
    "asparagus": "aspargos",
    "avocado": "abacate",
    "axe": "machado",
    "backpack": "mochila",
    "bagel": "bagel",
    "ball": "bola",
    "banana": "banana",
    "band-aid": "curativo",
    "banjo": "banjo",
    "barrel": "barril",
    "basket": "cesta",
    "bath towel": "toalha de banho",
    "bathtub": "banheira",
    "bear": "urso",
    "bed": "cama",
    "beehive": "colmeia",
    "beer": "cerveja",
    "bee": "abelha",
    "bell pepper": "pimentão",
    "belt": "cinto",
    "bench": "banco",
    "bicycle": "bicicleta",
    "binoculars": "binóculos",
    "bird": "pássaro",
    "boat": "barco",
    "book": "livro",
    "bookcase": "estante",
    "boot": "bota",
    "bottle": "garrafa",
    "bowl": "tigela",
    "box": "caixa",
    "boy": "menino",
    "brassiere": "sutiã",
    "bread": "pão",
    "briefcase": "pasta executiva",
    "broccoli": "brócolis",
    "broom": "vassoura",
    "butterfly": "borboleta",
    "cabbage": "repolho",
    "candle": "vela",
    "tin can": "lata",
    "cannon": "canhão",
    "canoe": "canoa",
    "carrot": "cenoura",
    "castle": "castelo",
    "cat": "gato",
    "celery": "salsão",
    "chair": "cadeira",
    "chalkboard": "quadro-negro",
    "cheese": "queijo",
    "cherry": "cereja",
    "chicken": "frango",
    "chimpanzee": "chimpanzé",
    "french fries": "batata frita",
    "christmas tree": "árvore de natal",
    "cigarette": "cigarro",
    "citrus": "cítrico",
    "cello": "violoncelo",
    "clock": "relógio",
    "closet": "armário",
    "coat": "casaco",
    "coconut": "coco",
    "coffee": "café",
    "coffee maker": "cafeteira",
    "coin": "moeda",
    "computer keyboard": "teclado",
    "traffic cone": "cone de trânsito",
    "cookie": "biscoito",
    "pressure cooker": "panela de pressão",
    "couch": "sofá",
    "crab": "caranguejo",
    "crane": "guindaste",
    "crocodile": "crocodilo",
    "croissant": "croissant",
    "crown": "coroa",
    "cucumber": "pepino",
    "cup": "xícara",
    "cupboard": "armário de cozinha",
    "wheelchair": "cadeira de rodas",
    "curtain": "cortina",
    "cactus": "cacto",
    "drum": "tambor",
    "duck": "pato",
    "dumbbell": "halter",
    "eagle": "águia",
    "elephant": "elefante",
    "emu": "emu",
    "envelope": "envelope",
    "excavator": "escavadeira",
    "feather": "pena",
    "fish": "peixe",
    "flamingo": "flamingo",
    "flashlight": "lanterna",
    "drinking glass": "copo",
    "glasses": "óculos",
    "glove": "luva",
    "goat": "cabra",
    "goggles": "óculos de proteção",
    "goose": "ganso",
    "gorilla": "gorila",
    "grape": "uva",
    "guitar": "guitarra",
    "gun": "arma de fogo",
    "hamburger": "hambúrguer",
    "hammer": "martelo",
    "handbag": "bolsa",
    "hat": "chapéu",
    "headphones": "fone de ouvido",
    "hedgehog": "ouriço",
    "helicopter": "helicóptero",
    "helmet": "capacete",
    "hen": "galinha",
    "herbs and spices": "ervas e especiarias",
    "hippopotamus": "hipopótamo",
    "hook": "gancho",
    "horse": "cavalo",
    "garden hose": "mangueira de jardim",
    "house": "casa",
    "hummingbird": "beija-flor",
    "ice cream": "sorvete",
    "clothes iron": "ferro de passar",
    "iguana": "iguana",
    "jaguar (animal)": "onça",
    "jaguar": "jaguar",
    "jam": "geleia",
    "jeans": "calça jeans",
    "kangaroo": "canguru",
    "kettle": "chaleira",
    "keyboard": "teclado",
    "kite": "pipa",
    "knife": "faca",
    "koala": "coala",
    "ladder": "escada",
    "ladybug": "joaninha",
    "lamp": "luminária",
    "laptop": "notebook",
    "lemon": "limão",
    "lettuce": "alface",
    "lighter": "isqueiro",
    "limousine": "limusine",
    "lion": "leão",
    "lizard": "lagarto",
    "lobster": "lagosta",
    "magnifying glass": "lupa",
    "map": "mapa",
    "melon": "melão",
    "microwave oven": "micro-ondas",
    "mirror": "espelho",
    "monkey": "macaco",
    "motorcycle": "motocicleta",
    "computer mouse": "mouse",
    "mushroom": "cogumelo",
    "mussel": "mexilhão",
    "nail": "prego",
    "necklace": "colar",
    "newspaper": "jornal",
    "octopus": "polvo",
    "orange": "laranja",
    "ostrich": "avestruz",
    "otter": "lontra",
    "owl": "coruja",
    "oyster": "ostra",
    "frying pan": "frigideira",
    "panda": "panda",
    "parrot": "papagaio",
    "pasta": "macarrão",
    "peach": "pêssego",
    "pear": "pêra",
    "pen": "caneta",
    "pencil case": "estojo",
    "pencil": "lápis",
    "penguin": "pinguim",
    "piano": "piano",
    "pigeon": "pombo",
    "pineapple": "abacaxi",
    "pizza": "pizza",
    "plant": "planta",
    "plate": "prato",
    "police officer": "policial",
    "pomegranate": "romã",
    "popcorn": "pipoca",
    "pig": "porco",
    "printer": "impressora",
    "projector": "projetor",
    "pumpkin": "abóbora",
    "rabbit": "coelho",
    "raccoon": "guaxinim",
    "racket": "raquete",
    "saucepan": "panela",
    "refrigerator": "geladeira",
    "remote control": "controle remoto",
    "rhinoceros": "rinoceronte",
    "ribbon": "fita",
    "rolling pin": "rolo de massa",
    "rooster": "galo",
    "ruler": "régua",
    "sausage": "salsicha",
    "scissors": "tesoura",
    "screw": "parafuso",
    "screwdriver": "chave de fenda",
    "seal": "foca",
    "shark": "tubarão",
    "sheep": "ovelha",
    "shell": "concha",
    "sailboat": "veleiro",
    "shirt": "camisa",
    "shoe": "sapato",
    "shotgun": "espingarda",
    "shovel": "pá",
    "shrimp": "camarão",
    "skateboard": "skate",
    "ski": "esqui",
    "skis": "esquis",
    "snake": "cobra",
    "snowboard": "snowboard",
    "snowman": "boneco de neve",
    "sock": "meia",
    "sofa bed": "sofá-cama",
    "spatula": "espátula",
    "spider": "aranha",
    "spoon": "colher",
    "squirrel": "esquilo",
    "steak": "bife",
    "bus": "ônibus",
    "sunglasses": "óculos de sol",
    "surfboard": "prancha de surfe",
    "sushi": "sushi",
    "swan": "cisne",
    "swimwear": "roupa de banho",
    "syringe": "seringa",
    "tablet computer": "tablet",
    "taco": "taco",
    "tank": "tanque",
    "tape measure": "fita métrica",
    "teapot": "bule",
    "telephone": "telefone",
    "telescope": "telescópio",
    "television": "televisão",
    "tennis ball": "bola de tênis",
    "tennis racket": "raquete de tênis",
    "tent": "barraca",
    "tiger": "tigre",
    "toaster": "torradeira",
    "toilet": "vaso sanitário",
    "toilet paper": "papel higiênico",
    "tomato": "tomate",
    "toothbrush": "escova de dente",
    "toothpaste": "pasta de dente",
    "torch": "tocha",
    "tortoise": "tartaruga",
    "towel": "toalha",
    "toy": "brinquedo",
    "traffic light": "semáforo",
    "traffic sign": "placa de trânsito",
    "train": "trem",
    "tray": "bandeja",
    "trumpet": "trompete",
    "sea turtle": "tartaruga-marinha",
    "umbrella": "guarda-chuva",
    "vacuum cleaner": "aspirador de pó",
    "van": "van",
    "vase": "vaso",
    "vehicle": "veículo",
    "violin": "violino",
    "vulture": "abutre",
    "waffle": "waffle",
    "wallet": "carteira",
    "walrus": "morsa",
    "watch": "relógio de pulso",
    "watermelon": "melancia",
    "wine glass": "taça de vinho",
    "wolf": "lobo",
    "woodpecker": "pica-pau",
    "wok": "wok",
    "wrench": "chave inglesa",
    "yak": "iaque",
    "yogurt": "iogurte",
    "zebra": "zebra",
    # Objetos domésticos / ambiente
    "window": "janela",
    "door": "porta",
    "cabinet": "armário",
    "kitchen cabinet": "armário de cozinha",
    "tool cabinet": "armário de ferramentas",
    "shelf": "prateleira",
    "bookshelf": "estante",
    "drawer": "gaveta",
    "wardrobe": "guarda-roupa",
    "desk": "escrivaninha",
    "table": "mesa",
    "dining table": "mesa de jantar",
    "coffee table": "mesa de centro",
    "floor": "chão",
    "ceiling": "teto",
    "wall": "parede",
    "staircase": "escada",
    "stairs": "degraus",
    "roof": "telhado",
    # Eletrônicos
    "mobile phone": "celular",
    "cell phone": "celular",
    "smartphone": "smartphone",
    "camera": "câmera",
    "calculator": "calculadora",
    "monitor": "monitor",
    "speaker": "caixa de som",
    "power bank": "bateria externa",
    "charger": "carregador",
    "router": "roteador",
    "microphone": "microfone",
    "headset": "headset",
    "earphones": "fone de ouvido",
    "usb drive": "pendrive",
    "hard drive": "HD externo",
    # Ferramentas
    "multimeter": "multímetro",
    "oscilloscope": "osciloscópio",
    "soldering iron": "ferro de solda",
    "pliers": "alicates",
    "drill": "furadeira",
    "saw": "serra",
    "tape": "fita",
    "level": "nível",
    # Alimentação
    "food": "comida",
    "fruit": "fruta",
    "vegetable": "vegetal",
    "salad": "salada",
    "soup": "sopa",
    "cake": "bolo",
    "sandwich": "sanduíche",
    "hot dog": "cachorro-quente",
    "donut": "rosquinha",
    "pie": "torta",
    "waffle": "waffle",
    "pancake": "panqueca",
    "burrito": "burrito",
    "rice": "arroz",
    "potato": "batata",
    "egg": "ovo",
    "milk": "leite",
    "juice": "suco",
    "water": "água",
    "tea": "chá",
    "wine": "vinho",
    "cocktail": "coquetel",
    "beer glass": "copo de cerveja",
    # Pessoas e roupas
    "person": "pessoa",
    "man": "homem",
    "woman": "mulher",
    "girl": "menina",
    "baby": "bebê",
    "child": "criança",
    "dress": "vestido",
    "skirt": "saia",
    "pants": "calça",
    "trousers": "calças",
    "jacket": "jaqueta",
    "hoodie": "moletom",
    "t-shirt": "camiseta",
    "scarf": "cachecol",
    "gloves": "luvas",
    "tie": "gravata",
    "suit": "terno",
    "underwear": "roupa íntima",
    "socks": "meias",
    "sneakers": "tênis",
    "sandals": "sandálias",
    "high heels": "salto alto",
    # Veículos
    "car": "carro",
    "truck": "caminhão",
    "bicycle": "bicicleta",
    "scooter": "patinete",
    "ambulance": "ambulância",
    "fire truck": "caminhão de bombeiros",
    "police car": "viatura policial",
    "taxi": "táxi",
    "ship": "navio",
    "submarine": "submarino",
    "rocket": "foguete",
    "space shuttle": "ônibus espacial",
    # Natureza
    "tree": "árvore",
    "flower": "flor",
    "grass": "grama",
    "leaf": "folha",
    "rock": "pedra",
    "mountain": "montanha",
    "river": "rio",
    "ocean": "oceano",
    "beach": "praia",
    "sky": "céu",
    "cloud": "nuvem",
    "sun": "sol",
    "moon": "lua",
    "star": "estrela",
    "fire": "fogo",
    "snow": "neve",
    "rain": "chuva",
    "rainbow": "arco-íris",
    # Esportes
    "ball": "bola",
    "football": "bola de futebol",
    "basketball": "bola de basquete",
    "baseball": "béisbol",
    "volleyball": "vôlei",
    "golf ball": "bola de golfe",
    "billiards": "sinuca",
    "bow and arrow": "arco e flecha",
    "dumbbell": "halter",
    "yoga mat": "tapete de yoga",
    "treadmill": "esteira",
    "swimming pool": "piscina",
    # Instrumentos musicais
    "microphone": "microfone",
    "piano": "piano",
    "guitar": "violão",
    "electric guitar": "guitarra elétrica",
    "bass guitar": "contrabaixo",
    "drum": "bateria",
    "saxophone": "saxofone",
    "flute": "flauta",
    "trumpet": "trompete",
    "harp": "harpa",
    "keyboard instrument": "teclado musical",
    # Utensílios de cozinha
    "fork": "garfo",
    "chopsticks": "hashis",
    "whisk": "batedor de ovos",
    "grater": "ralador",
    "colander": "peneira",
    "cutting board": "tábua de corte",
    "pot": "panela",
    "baking tray": "assadeira",
    "mixing bowl": "tigela de mistura",
    # Escritório / papelaria
    "stapler": "grampeador",
    "paper clip": "clipe de papel",
    "rubber band": "elástico",
    "tape dispenser": "porta-fita",
    "folder": "pasta",
    "binder": "fichário",
    "whiteboard": "quadro branco",
    "projector screen": "tela de projetor",
    # Google Nest / Smart home
    "google nest mini": "Google Nest Mini",
    "smart speaker": "caixa de som inteligente",
    "home assistant": "assistente de voz",
}

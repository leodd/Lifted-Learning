import numpy as np
import torch
from torch import nn
from demo.iris_prediction.iris_loader import load_iris_data_fold


res = list()

for fold in range(5):
    train_data, test_data = load_iris_data_fold('iris', fold, folds=5)

    m = len(train_data)

    x = train_data[:, [0, 1, 2, 3]]
    y = train_data[:, 4]
    x = torch.from_numpy(x).type(torch.float32)
    y = torch.from_numpy(y).type(torch.long)

    model = nn.Sequential(
        nn.Linear(4, 64), nn.ReLU(),
        nn.Linear(64, 32), nn.ReLU(),
        nn.Linear(32, 3)
    )

    optimizer = torch.optim.Adam(model.parameters(), 0.001, weight_decay=0.0001)
    criterion = nn.CrossEntropyLoss()

    for _ in range(1000):
        optimizer.zero_grad()
        out = model(x)
        loss = criterion(out, y)
        loss.backward()
        optimizer.step()
        # print(loss)

    x = test_data[:, [0, 1, 2, 3]]
    y = test_data[:, 4]
    x = torch.from_numpy(x).type(torch.float32)
    y = torch.from_numpy(y).type(torch.long)

    with torch.no_grad():
        out = model(x)
        y_predict = out.argmax(dim=1)

    res.append(torch.mean((y_predict == y).type(torch.float)).item())
    print(res[-1])

print(res, np.mean(res), np.var(res))

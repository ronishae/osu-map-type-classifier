import numpy as np
import pandas as pd
from sklearn.naive_bayes import GaussianNB
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score

if __name__ == "__main__":
    print('Starting classifier...')
    np.random.seed(1)
    np.set_printoptions(precision=4, suppress=True)

    df = pd.read_csv('output.csv')

    # print(df.head())

    X = df.iloc[1:, :-1].values
    y = df.iloc[1:, -1].values

    X_train, X_test, y_train, y_test = train_test_split(X,y, test_size=0.20, random_state=1)
    stdsc = StandardScaler()
    X_train_std = stdsc.fit_transform(X_train)
    X_test_std = stdsc.transform(X_test)

    clf = GaussianNB()
    clf.fit(X_train_std, y_train)
    GaussianNB(priors=None)
    y_pred = clf.predict(X_test_std)

    acc = accuracy_score(y_true=y_test, y_pred=y_pred)
    print(f'Complete! \nAccuracy: {acc}')
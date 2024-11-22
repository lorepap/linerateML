import os
import csv
import itertools
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from subprocess import call
from sklearn.preprocessing import LabelEncoder
from sklearn.tree import DecisionTreeClassifier, export_graphviz, export_text
from sklearn.model_selection import train_test_split
from sklearn.metrics import confusion_matrix, f1_score
from sklearn.preprocessing import LabelEncoder
from sklearn.inspection import permutation_importance
from sklearn.feature_selection import RFE
from statistics import median, mean

def read_and_clean_dataset(folder):
	filenames  = [
	'UNSW_NB15_training-set.csv',
	'UNSW_NB15_testing-set.csv',
	]
	
	dataset = []
	for filename in filenames:
		dataset.append(pd.read_csv(os.path.join(folder, filename)))

	dataset = pd.concat(dataset)
	
	# Removing rows with missing data and rows with infinite data
	dataset = dataset.replace([np.inf, -np.inf], np.nan)
	dataset = dataset.dropna()
	return dataset

def preprocess_dataset(dataset, use_switch_features, bin_threshold):
	# Keeping some columns only
	dataset = dataset.drop(['label', 'service', 'state', 'proto', 'id'], axis=1)
	if use_switch_features:
		dataset = dataset.loc[:, dataset.columns.intersection(['dur', 'spkts', 'dpkts', 'sbytes',
       'dbytes', 'sttl', 'dttl', 'sinpkt', 'dinpkt', 'swin', 'stcpb', 'dtcpb', 'dwin',
       'tcprtt', 'synack', 'ackdat', 'ct_dst_ltm',
       'ct_src_dport_ltm', 'ct_dst_sport_ltm', 'ct_dst_src_ltm', 'ct_src_ltm', 'attack_cat'])]
	
	if bin_threshold == -1:
		dataset.loc[dataset.attack_cat == 'Normal', 'attack_cat'] = 'Normal'
		dataset.loc[dataset.attack_cat != 'Normal', 'attack_cat'] = 'MALICIOUS'
	else:
		counts = dataset.attack_cat.value_counts()
		low_count_classes = counts[counts < bin_threshold]
		low_count_classes = low_count_classes.index.ravel()
		for c in low_count_classes:
			dataset.loc[dataset.attack_cat == c, 'attack_cat'] = 'OtherMalicious'

	return dataset

def plot_feature_importance_mdi(model, features, filename):
	importances = pd.DataFrame({'feature' : features, 'importance' : model.feature_importances_})
	importances = importances.sort_values('importance', ascending=False).set_index('feature')
	plt.rcParams['figure.figsize'] = (15, 5)
	fig, ax = plt.subplots()
	importances.plot.bar(ax=ax)
	ax.set_title("Feature importances using MDI")
	ax.set_ylabel("Mean decrease in impurity")
	fig.tight_layout()
	plt.savefig(filename + 'mdi.pdf', bbox_inches='tight')
	plt.close()

def plot_permutation_importance(model, X_test, y_test, features, filename):
	result = permutation_importance(model, X_test, y_test, n_repeats=10, random_state=42, n_jobs=2)
	importances = pd.DataFrame({'feature':features, 'importance' : result.importances_mean})
	importances = importances.sort_values('importance', ascending=False).set_index('feature')
	plt.rcParams['figure.figsize'] = (10, 5)
	fig, ax = plt.subplots()
	importances.plot.bar(ax=ax)
	ax.set_title("Feature importances using permutation on full model")
	ax.set_ylabel("Mean accuracy decrease")
	fig.tight_layout()
	plt.savefig(filename + 'permutation.pdf', bbox_inches='tight')
	plt.close()

def select_features(num_features, model, x, y, features):
	rfe = RFE(model, n_features_to_select=num_features)
	rfe.fit(x, y)
	feature_map = [(i, v) for i, v in itertools.zip_longest(rfe.get_support(), features)]
	map = [i[0] for i in feature_map]
	features = []
	for i in feature_map:
		if i[0]:
			features.append(i[1])

	return map, features

def main():
	os.mkdir('results-nb15')
	experiments = [(8, 256, 3, True, 3000), (7, 128, 4, True, 3000), (6, 64, 6, True, 3000), (5, 32, 10, True, 3000), (4, 16, 14, True, 3000), (14, 16384, 2, True, 3000), (13, 8192, 4, True, 3000), (12, 4096, 5, True, 3000), (11, 2096, 8, True, 3000), (10, 1024, 14, True, 3000)]
	

	boxs = []
	results = []
	for exp in experiments:
		# Training random forest tree
		filename = 'D' + str(exp[0]) + '-L' + str(exp[1]) + '-F' + str(exp[2]) + '-SWITCHFEATURES' + str(exp[3])
		print(filename)

		dataset = read_and_clean_dataset('UNSW-NB15')
		dataset = preprocess_dataset(dataset, exp[3], exp[4])

		print('Shape:', dataset.shape)
		print(dataset.attack_cat.value_counts())
		num_classes = len(dataset.attack_cat.unique())
		features = dataset.columns.tolist()[:-1]
		
		# Encoding labels
		labelencoder = LabelEncoder()
		y = labelencoder.fit_transform(dataset.attack_cat)
		dataset = dataset.drop(['attack_cat'], axis=1).values

		# Splitting up train and test sets
		X_train, X_test, y_train, y_test = train_test_split(dataset, y, train_size = 0.75, test_size = 0.25, stratify = y)

		model = DecisionTreeClassifier(max_depth=exp[0], max_leaf_nodes=exp[1], criterion='entropy', class_weight='balanced')

		map, features = select_features(exp[2], model, X_train, y_train, features)
		X_train = pd.DataFrame(X_train)
		X_test = pd.DataFrame(X_test)
		X_train = X_train.iloc[:, map]
		X_test = X_test.iloc[:, map]

		model.fit(X_train, y_train)

		# plot_feature_importance_mdi(model, features, filename)
		# plot_permutation_importance(model, X_test, y_test, features, filename)
		# return

		y_predict = model.predict(X_test)
		y_train_predict = model.predict(X_train)
		cm_test = confusion_matrix(y_test, y_predict)
		cm_train = confusion_matrix(y_train, y_train_predict)
		cm_test = cm_test.tolist()
		cm_train = cm_train.tolist()

		class_f1 = f1_score(y_test, y_predict, average=None)
		macro_f1 = f1_score(y_test, y_predict, average='macro')
		results.append(class_f1)
		boxs.append({
			'label' : 'Depth ' + str(exp[0]) + '\nLeaves ' + str(exp[1]) + '\nFeatures ' + str(exp[2]),
			'whislo': min(class_f1),
			'q1'    : min(class_f1),
			'med'   : median(class_f1),
			'q3'    : max(class_f1),
			'whishi': max(class_f1),
			'mean' : mean(class_f1),
			'fliers': []
		})
		print('Test set - Macro F1', macro_f1)

		lab = labelencoder.inverse_transform([x for x in range(num_classes)])
		lab = lab.tolist()
		for i in range(len(cm_test)):
			cm_test[i].insert(0, 'Actual-' + lab[i])
			cm_train[i].insert(0, 'Actual-' + lab[i])

		lab.insert(0, 'Predicted-->')

		with open('results-nb15/results.csv', 'a') as my_csv:
			csvWriter = csv.writer(my_csv, delimiter=',')
			csvWriter.writerow([filename])
			csvWriter.writerow([len(features)] + features)
			csvWriter.writerow(lab)
			csvWriter.writerows(cm_test)
			csvWriter.writerow(['F1 score'] + class_f1.tolist() + [macro_f1])
			csvWriter.writerow(lab)
			csvWriter.writerows(cm_train)
			csvWriter.writerow(['========================================='])

		out_filename = 'results-nb15/' + os.path.split(filename)[-1].split('.')[0]
		dot_filename = out_filename + '.dot'
		export_graphviz(model, out_file=dot_filename,  class_names=labelencoder.inverse_transform([x for x in range(num_classes)]), feature_names=features, proportion = True)
		call(['dot', '-Tpdf', dot_filename, '-o', out_filename + '.pdf'])
		call(['rm', dot_filename])
		with open('results-nb15/results.txt', 'a') as my_txt:
			my_txt.write(filename + '\n')
			my_txt.write(export_text(model, feature_names=features))
			my_txt.write('=========================================\n')

	fig, ax = plt.subplots()
	ax.bxp(boxs, showfliers=False, showcaps=False, showmeans=True)
	ax.set_ylabel('F1 score')
	plt.savefig('results-nb15/nb15-box-plot.pdf', bbox_inches='tight')
	plt.close()

if __name__ == '__main__':
	main()
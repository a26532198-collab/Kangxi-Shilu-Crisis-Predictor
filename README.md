# Kangxi-Shilu-Crisis-Predictor
This study applies data science to the Veritable Records of Kangxi to predict historical crises. Using N-gram tokenization and Lasso-regularized Logistic Regression, it identifies linguistic predictors of documented conflicts. This research validates quantitative text mining as a tool for empirical Digital Humanities analysis.

## 🛠 Technical Implementation
- **Feature Engineering**: Extracted Bi-gram and Tri-gram from Classical Chinese text to capture semantic units.
- **Handling Sparsity**: Managed high-dimensional sparse matrices resulting from all-word extraction.
- **Regularization**: Applied **Lasso (L1)** to perform automatic feature selection, filtering out statistically insignificant functional characters (Stopwords).
- **Evaluation**: Achieved **85% Accuracy** in predicting historical crisis years.

## License
- Code: [MIT License](LICENSE)
- Data: The raw data is sourced from the [National Institute of Korean History](http://db.history.go.kr/).
- Analysis Content: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

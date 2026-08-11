(() => {
    const operationalSectionSelect = document.getElementById('operationalSection');
    const jobTitleSelect = document.getElementById('jobTitle');
    const labelsElement = document.getElementById('register-female-job-title-labels');

    if (!operationalSectionSelect || !jobTitleSelect || !labelsElement) {
        return;
    }

    const femaleLabels = JSON.parse(labelsElement.textContent);
    const maleLabels = Object.fromEntries(
        [...jobTitleSelect.options].map((option) => [option.value, option.textContent])
    );

    const updateJobTitleLabels = () => {
        const labels = operationalSectionSelect.value === 'female' ? femaleLabels : maleLabels;
        [...jobTitleSelect.options].forEach((option) => {
            option.textContent = labels[option.value] || maleLabels[option.value];
        });
    };

    operationalSectionSelect.addEventListener('change', updateJobTitleLabels);
    updateJobTitleLabels();
})();
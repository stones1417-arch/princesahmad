(() => {
    const operationalSectionSelect = document.querySelector('[data-field="operational_section"]');
    const jobTitleSelect = document.getElementById('id_job_title');
    const labelsElement = document.getElementById('employee-job-title-labels');

    if (!operationalSectionSelect || !jobTitleSelect || !labelsElement) {
        return;
    }

    const jobTitleLabels = JSON.parse(labelsElement.textContent);

    const updateJobTitleLabels = () => {
        const labels = operationalSectionSelect.value === 'female'
            ? jobTitleLabels.female
            : jobTitleLabels.male;

        [...jobTitleSelect.options].forEach((option) => {
            option.textContent = labels[option.value] || jobTitleLabels.male[option.value];
        });
    };

    operationalSectionSelect.addEventListener('change', updateJobTitleLabels);
    updateJobTitleLabels();
})();
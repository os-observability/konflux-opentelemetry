package main

import (
	"bufio"
	"context"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strings"

	"github.com/spf13/cobra"
	metav1 "k8s.io/apimachinery/pkg/apis/meta/v1"
	"k8s.io/apimachinery/pkg/apis/meta/v1/unstructured"
	"k8s.io/apimachinery/pkg/runtime/schema"
	"k8s.io/client-go/dynamic"
	"k8s.io/client-go/tools/clientcmd"
)

const (
	bundleEnvPath      = "../bundle-patch/bundle.env"
	defaultNamespace   = "rhosdt-tenant"
)

type PullspecInfo struct {
	ComponentName     string
	EnvVarName        string
	CurrentPullspec   string
	LatestPullspec    string
	LastBuiltCommit   string
}

type ReleaseCondition struct {
	Type    string
	Status  string
	Message string
	Reason  string
}

func main() {
	var namespace string

	var rootCmd = &cobra.Command{
		Use:   "konflux-tool",
		Short: "A CLI tool for managing Konflux components",
		Long: `A CLI tool for managing Konflux components.

The tool expects ./bundle-patch/bundle.env to have comments in the format:
# konflux component: <component-name>
for every component that should be checked.`,
	}

	var checkBundleCmd = &cobra.Command{
		Use:   "check-bundle",
		Short: "Check if pullspecs in bundle.env are up to date",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runCheckBundle(cmd, args, namespace)
		},
	}

	var checkReleaseCmd = &cobra.Command{
		Use:   "check-release",
		Short: "Check if bundle.env images are included in the latest snapshot and find the corresponding release",
		RunE: func(cmd *cobra.Command, args []string) error {
			return runCheckRelease(cmd, args, namespace)
		},
	}

	// Add namespace flag to both commands
	checkBundleCmd.Flags().StringVarP(&namespace, "namespace", "n", defaultNamespace, "Kubernetes namespace to query")
	checkReleaseCmd.Flags().StringVarP(&namespace, "namespace", "n", defaultNamespace, "Kubernetes namespace to query")

	rootCmd.AddCommand(checkBundleCmd)
	rootCmd.AddCommand(checkReleaseCmd)

	if err := rootCmd.Execute(); err != nil {
		fmt.Fprintf(os.Stderr, "Error: %v\n", err)
		os.Exit(1)
	}
}

func runCheckBundle(cmd *cobra.Command, args []string, namespace string) error {
	// Read bundle.env file
	pullspecs, err := readBundleEnv()
	if err != nil {
		return fmt.Errorf("failed to read bundle.env: %w", err)
	}

	// Create Kubernetes client
	client, err := createKubernetesClient()
	if err != nil {
		return fmt.Errorf("failed to create Kubernetes client: %w", err)
	}

	// Check each component
	var outdatedPullspecs []PullspecInfo
	for _, pullspec := range pullspecs {
		latestPullspec, lastBuiltCommit, err := getLatestPullspecAndCommit(client, pullspec.ComponentName, namespace)
		if err != nil {
			fmt.Printf("Warning: failed to get latest pullspec for %s: %v\n", pullspec.ComponentName, err)
			continue
		}

		pullspec.LatestPullspec = latestPullspec
		pullspec.LastBuiltCommit = lastBuiltCommit
		if pullspec.CurrentPullspec != latestPullspec {
			outdatedPullspecs = append(outdatedPullspecs, pullspec)
		}
	}

	// Print results
	if len(outdatedPullspecs) == 0 {
		fmt.Println("All pullspecs are up to date!")
		return nil
	}

	fmt.Printf("Found %d outdated pullspec(s):\n\n", len(outdatedPullspecs))
	for _, pullspec := range outdatedPullspecs {
		fmt.Printf("Component: %s\n", pullspec.ComponentName)
		fmt.Printf("  Environment Variable: %s\n", pullspec.EnvVarName)
		fmt.Printf("  Current:  %s\n", pullspec.CurrentPullspec)
		fmt.Printf("  Latest:   %s\n", pullspec.LatestPullspec)
		fmt.Printf("  Last Built Commit: %s\n", pullspec.LastBuiltCommit)
		fmt.Println()
	}

	// Exit with code 1 if pullspecs are outdated
	os.Exit(1)
	return nil // This will never be reached but satisfies the compiler
}

func readBundleEnv() ([]PullspecInfo, error) {
	file, err := os.Open(bundleEnvPath)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	var pullspecs []PullspecInfo
	scanner := bufio.NewScanner(file)

	// Regex to match component comments and environment variables
	componentRegex := regexp.MustCompile(`^# konflux component: (.+)$`)
	envVarRegex := regexp.MustCompile(`^([A-Z_]+)=(.+)$`)

	var currentComponent string

	for scanner.Scan() {
		line := strings.TrimSpace(scanner.Text())

		// Skip empty lines and non-component comments
		if line == "" || (strings.HasPrefix(line, "#") && !componentRegex.MatchString(line)) {
			continue
		}

		// Check for component comment
		if matches := componentRegex.FindStringSubmatch(line); matches != nil {
			currentComponent = matches[1]
			continue
		}

		// Check for environment variable
		if matches := envVarRegex.FindStringSubmatch(line); matches != nil && currentComponent != "" {
			envVarName := matches[1]
			pullspec := matches[2]

			pullspecs = append(pullspecs, PullspecInfo{
				ComponentName:   currentComponent,
				EnvVarName:      envVarName,
				CurrentPullspec: pullspec,
			})

			// Reset current component after processing its pullspec
			currentComponent = ""
		}
	}

	if err := scanner.Err(); err != nil {
		return nil, err
	}

	return pullspecs, nil
}

func createKubernetesClient() (dynamic.Interface, error) {
	// Use the default kubeconfig path
	kubeconfig := filepath.Join(os.Getenv("HOME"), ".kube", "config")
	if kubeconfigEnv := os.Getenv("KUBECONFIG"); kubeconfigEnv != "" {
		kubeconfig = kubeconfigEnv
	}

	config, err := clientcmd.BuildConfigFromFlags("", kubeconfig)
	if err != nil {
		return nil, err
	}

	client, err := dynamic.NewForConfig(config)
	if err != nil {
		return nil, err
	}

	return client, nil
}

func getLatestPullspecAndCommit(client dynamic.Interface, componentName string, namespace string) (string, string, error) {
	// Define the GVR for Component custom resources
	componentGVR := schema.GroupVersionResource{
		Group:    "appstudio.redhat.com",
		Version:  "v1alpha1",
		Resource: "components",
	}

	// Get the component by name
	component, err := client.Resource(componentGVR).Namespace(namespace).Get(context.TODO(), componentName, metav1.GetOptions{})
	if err != nil {
		return "", "", err
	}

	// Extract the lastPromotedImage and lastBuiltCommit from status
	status, found, err := unstructured.NestedMap(component.Object, "status")
	if err != nil {
		return "", "", err
	}
	if !found {
		return "", "", fmt.Errorf("status not found in component %s", componentName)
	}

	lastPromotedImage, found, err := unstructured.NestedString(status, "lastPromotedImage")
	if err != nil {
		return "", "", err
	}
	if !found {
		return "", "", fmt.Errorf("lastPromotedImage not found in component %s status", componentName)
	}

	lastBuiltCommit, found, err := unstructured.NestedString(status, "lastBuiltCommit")
	if err != nil {
		return "", "", err
	}
	if !found {
		// lastBuiltCommit is optional, so we'll set it to "N/A" if not found
		lastBuiltCommit = "N/A"
	}

	return lastPromotedImage, lastBuiltCommit, nil
}

func runCheckRelease(cmd *cobra.Command, args []string, namespace string) error {
	// Read bundle.env file to get the expected images
	pullspecs, err := readBundleEnv()
	if err != nil {
		return fmt.Errorf("failed to read bundle.env: %w", err)
	}

	// Create Kubernetes client
	client, err := createKubernetesClient()
	if err != nil {
		return fmt.Errorf("failed to create Kubernetes client: %w", err)
	}

	// Get the most recent snapshot that contains all our images
	snapshotName, bundlePullspec, err := findSnapshotWithImagesAndBundle(client, pullspecs, namespace)
	if err != nil {
		fmt.Printf("Error: %v\n", err)
		fmt.Println("Suggestion: Trigger a build with:")
		fmt.Println("kubectl annotate components/otel-bundle-main build.appstudio.openshift.io/request=trigger-pac-build")
		os.Exit(1)
	}

	// Find the release that references this snapshot
	releaseName, releaseConditions, err := findReleaseForSnapshotWithConditions(client, snapshotName, namespace)
	if err != nil {
		return fmt.Errorf("failed to find release for snapshot %s: %w", snapshotName, err)
	}

	fmt.Printf("Snapshot: %s\n", snapshotName)
	fmt.Printf("Release: %s\n", releaseName)
	if bundlePullspec != "" {
		fmt.Printf("Bundle Pullspec: %s\n", bundlePullspec)
	}

	// Print Released condition if it exists
	var isReleased bool
	for _, condition := range releaseConditions {
		if condition.Type == "Released" {
			fmt.Printf("Release Status: %s\n", condition.Status)
			if condition.Message != "" {
				fmt.Printf("Release Message: %s\n", condition.Message)
			}
			if condition.Reason != "" {
				fmt.Printf("Release Reason: %s\n", condition.Reason)
			}
			isReleased = strings.ToLower(condition.Status) == "true"
			break
		}
	}

	// Print summary of component state and release status
	fmt.Println()
	fmt.Printf("Summary: All components from bundle.env are included in snapshot %s", snapshotName)
	if isReleased {
		fmt.Printf(" and have been successfully released.\n")
	} else {
		fmt.Printf(" but have not been released yet.\n")
	}

	return nil
}

func findSnapshotWithImagesAndBundle(client dynamic.Interface, expectedPullspecs []PullspecInfo, namespace string) (string, string, error) {
	// Define the GVR for Snapshot custom resources
	snapshotGVR := schema.GroupVersionResource{
		Group:    "appstudio.redhat.com",
		Version:  "v1alpha1",
		Resource: "snapshots",
	}

	// Get all snapshots ordered by creation time (most recent first)
	snapshots, err := client.Resource(snapshotGVR).Namespace(namespace).List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		return "", "", fmt.Errorf("failed to list snapshots: %w", err)
	}

	// Sort snapshots by creation time (most recent first) using Before()
	sort.Slice(snapshots.Items, func(i, j int) bool {
		timeI := snapshots.Items[i].GetCreationTimestamp()
		timeJ := snapshots.Items[j].GetCreationTimestamp()
		return timeJ.Before(&timeI)
	})

	// Extract expected image pullspecs from bundle.env
	expectedImages := make(map[string]bool)
	for _, pullspec := range expectedPullspecs {
		expectedImages[pullspec.CurrentPullspec] = false
	}

	// Check each snapshot to see if it contains all our images
	for _, snapshot := range snapshots.Items {
		bundlePullspec := extractBundlePullspec(snapshot)
		if containsAllImages(snapshot, expectedImages) {
			return snapshot.GetName(), bundlePullspec, nil
		}
	}

	return "", "", fmt.Errorf("no snapshot found containing all images from bundle.env")
}

func extractBundlePullspec(snapshot unstructured.Unstructured) string {
	// Get spec.components from snapshot
	spec, found, err := unstructured.NestedMap(snapshot.Object, "spec")
	if err != nil || !found {
		return ""
	}

	components, found, err := unstructured.NestedSlice(spec, "components")
	if err != nil || !found {
		return ""
	}

	// Look for the bundle component (usually has "bundle" in the name)
	for _, comp := range components {
		if component, ok := comp.(map[string]interface{}); ok {
			if name, found, err := unstructured.NestedString(component, "name"); err == nil && found {
				if strings.Contains(strings.ToLower(name), "bundle") {
					if containerImage, found, err := unstructured.NestedString(component, "containerImage"); err == nil && found {
						return containerImage
					}
				}
			}
		}
	}

	return ""
}

func containsAllImages(snapshot unstructured.Unstructured, expectedImages map[string]bool) bool {
	// Reset the found status
	for image := range expectedImages {
		expectedImages[image] = false
	}

	// Get spec.components from snapshot
	spec, found, err := unstructured.NestedMap(snapshot.Object, "spec")
	if err != nil || !found {
		return false
	}

	components, found, err := unstructured.NestedSlice(spec, "components")
	if err != nil || !found {
		return false
	}

	// Check each component's containerImage
	for _, comp := range components {
		if component, ok := comp.(map[string]interface{}); ok {
			if containerImage, found, err := unstructured.NestedString(component, "containerImage"); err == nil && found {
				if _, exists := expectedImages[containerImage]; exists {
					expectedImages[containerImage] = true
				}
			}
		}
	}

	// Check if all expected images were found
	for _, found := range expectedImages {
		if !found {
			return false
		}
	}

	return true
}

func findReleaseForSnapshotWithConditions(client dynamic.Interface, snapshotName string, namespace string) (string, []ReleaseCondition, error) {
	// Define the GVR for Release custom resources
	releaseGVR := schema.GroupVersionResource{
		Group:    "appstudio.redhat.com",
		Version:  "v1alpha1",
		Resource: "releases",
	}

	// Get all releases
	releases, err := client.Resource(releaseGVR).Namespace(namespace).List(context.TODO(), metav1.ListOptions{})
	if err != nil {
		return "", nil, fmt.Errorf("failed to list releases: %w", err)
	}

	// Find release that references our snapshot
	for _, release := range releases.Items {
		spec, found, err := unstructured.NestedMap(release.Object, "spec")
		if err != nil || !found {
			continue
		}

		if releaseSnapshot, found, err := unstructured.NestedString(spec, "snapshot"); err == nil && found {
			if releaseSnapshot == snapshotName {
				// Extract conditions from status
				var conditions []ReleaseCondition
				status, found, err := unstructured.NestedMap(release.Object, "status")
				if err == nil && found {
					if conditionsSlice, found, err := unstructured.NestedSlice(status, "conditions"); err == nil && found {
						for _, conditionInterface := range conditionsSlice {
							if conditionMap, ok := conditionInterface.(map[string]interface{}); ok {
								condition := ReleaseCondition{}
								if condType, found, err := unstructured.NestedString(conditionMap, "type"); err == nil && found {
									condition.Type = condType
								}
								if condStatus, found, err := unstructured.NestedString(conditionMap, "status"); err == nil && found {
									condition.Status = condStatus
								}
								if condMessage, found, err := unstructured.NestedString(conditionMap, "message"); err == nil && found {
									condition.Message = condMessage
								}
								if condReason, found, err := unstructured.NestedString(conditionMap, "reason"); err == nil && found {
									condition.Reason = condReason
								}
								conditions = append(conditions, condition)
							}
						}
					}
				}
				return release.GetName(), conditions, nil
			}
		}
	}

	return "", nil, fmt.Errorf("no release found referencing snapshot %s", snapshotName)
}